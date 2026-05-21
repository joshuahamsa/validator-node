#!/usr/bin/env python3
"""Tests for amend_lib.py"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amend_lib


class TestComputeWorkingSet(unittest.TestCase):
    """compute_working_set uses the `vetoed` field from the admin RPC as the vote source.

    vetoed: true  → your_vote "no"
    vetoed: false → your_vote "yes"
    vetoed: "Obsolete" → skipped
    enabled: true → skipped
    """

    def test_vetoed_false_gives_yes(self):
        features = {"HASH_A": {"name": "XChainBridge", "supported": True, "vetoed": False}}
        result = amend_lib.compute_working_set(features)
        self.assertEqual(result[0]["your_vote"], "yes")

    def test_vetoed_true_gives_no(self):
        features = {"HASH_A": {"name": "LendingProtocol", "supported": True, "vetoed": True}}
        result = amend_lib.compute_working_set(features)
        self.assertEqual(result[0]["your_vote"], "no")

    def test_vetoed_absent_gives_yes(self):
        # No vetoed field → not vetoed → yes
        features = {"HASH_A": {"name": "fixFoo", "supported": True}}
        result = amend_lib.compute_working_set(features)
        self.assertEqual(result[0]["your_vote"], "yes")

    def test_excludes_enabled(self):
        features = {
            "HASH_PENDING": {"name": "fixFoo", "supported": True, "vetoed": False},
            "HASH_ENABLED": {"name": "fixBar", "enabled": True, "supported": True},
        }
        result = amend_lib.compute_working_set(features)
        names = [a["name"] for a in result]
        self.assertIn("fixFoo", names)
        self.assertNotIn("fixBar", names)

    def test_excludes_rpc_obsolete(self):
        features = {"HASH_OBS": {"name": "Clawback", "supported": True, "vetoed": "Obsolete"}}
        result = amend_lib.compute_working_set(features)
        self.assertEqual(result, [])

    def test_majority_sorts_first(self):
        features = {
            "HASH_NO_MAJ": {"name": "Aardvark", "supported": True, "vetoed": False},
            "HASH_MAJ": {"name": "Zebra", "supported": True, "vetoed": False, "majority": 12345},
        }
        result = amend_lib.compute_working_set(features)
        self.assertEqual(result[0]["name"], "Zebra")

    def test_majority_flag_present(self):
        features = {"HASH_MAJ": {"name": "fixFoo", "supported": True, "vetoed": False, "majority": 99999}}
        result = amend_lib.compute_working_set(features)
        self.assertTrue(result[0]["majority"])

    def test_majority_flag_absent(self):
        features = {"HASH_A": {"name": "fixFoo", "supported": True, "vetoed": False}}
        result = amend_lib.compute_working_set(features)
        self.assertFalse(result[0]["majority"])

    def test_alphabetical_within_same_majority_bucket(self):
        features = {
            "HASH_Z": {"name": "Zebra", "supported": True, "vetoed": False},
            "HASH_A": {"name": "Aardvark", "supported": True, "vetoed": False},
        }
        result = amend_lib.compute_working_set(features)
        self.assertEqual(result[0]["name"], "Aardvark")


class TestUpdateCfgText(unittest.TestCase):
    def test_adds_to_amendments_section(self):
        cfg = "[amendments]\nexistinghash\n\n[server]\nport 6006\n"
        result = amend_lib.update_cfg_text(cfg, "newhash", "yes")
        lines = result.splitlines()
        amend_idx = lines.index("[amendments]")
        self.assertIn("newhash", lines[amend_idx + 1 : amend_idx + 3])

    def test_adds_to_veto_section(self):
        cfg = "[veto_amendments]\nexistinghash\n"
        result = amend_lib.update_cfg_text(cfg, "newhash", "no")
        self.assertIn("newhash", result)
        self.assertIn("[veto_amendments]", result)

    def test_removes_from_veto_when_voting_yes(self):
        cfg = "[veto_amendments]\nnewhash\n\n[amendments]\nother\n"
        result = amend_lib.update_cfg_text(cfg, "newhash", "yes")
        veto_section = result.split("[veto_amendments]")[1].split("[")[0]
        self.assertNotIn("newhash", veto_section)

    def test_removes_from_amendments_when_voting_no(self):
        cfg = "[amendments]\nnewhash\n\n[veto_amendments]\nother\n"
        result = amend_lib.update_cfg_text(cfg, "newhash", "no")
        amend_section = result.split("[amendments]")[1].split("[")[0]
        self.assertNotIn("newhash", amend_section)

    def test_creates_amendments_section_when_absent(self):
        cfg = "[server]\nport 6006\n"
        result = amend_lib.update_cfg_text(cfg, "newhash", "yes")
        self.assertIn("[amendments]", result)
        self.assertIn("newhash", result)

    def test_creates_veto_section_when_absent(self):
        cfg = "[server]\nport 6006\n"
        result = amend_lib.update_cfg_text(cfg, "newhash", "no")
        self.assertIn("[veto_amendments]", result)
        self.assertIn("newhash", result)


class TestSessionSaveLoad(unittest.TestCase):
    def test_roundtrip(self):
        amendments = [
            {"hash": "ABC", "name": "TestAmend", "your_vote": "no",
             "majority": False, "supported": True, "description": ""},
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            amend_lib.save_session(amendments, path=path)
            loaded = amend_lib.load_session(path=path)
            self.assertEqual(loaded[0]["hash"], "ABC")
            self.assertEqual(loaded[0]["vote"], "no")
        finally:
            os.unlink(path)


class TestAmendmentDescriptionParser(unittest.TestCase):
    SAMPLE_HTML = """
    <html><body>
    <h2 id="multisignreserve">MultiSignReserve</h2>
    <p>Reduces the reserve for multi-signing from 5 XRP to 1 XRP per signer.</p>
    <p>Second paragraph, should be ignored.</p>
    <h2 id="fix1781">fix1781</h2>
    <p>Fixes an edge case in payment path finding.</p>
    </body></html>
    """

    def test_parses_first_paragraph(self):
        parser = amend_lib._AmendmentDescriptionParser()
        parser.feed(self.SAMPLE_HTML)
        desc = parser.get_descriptions()
        self.assertEqual(desc["MultiSignReserve"],
                         "Reduces the reserve for multi-signing from 5 XRP to 1 XRP per signer.")

    def test_parses_multiple_amendments(self):
        parser = amend_lib._AmendmentDescriptionParser()
        parser.feed(self.SAMPLE_HTML)
        desc = parser.get_descriptions()
        self.assertIn("fix1781", desc)

    def test_only_first_paragraph_per_amendment(self):
        parser = amend_lib._AmendmentDescriptionParser()
        parser.feed(self.SAMPLE_HTML)
        desc = parser.get_descriptions()
        self.assertNotIn("Second paragraph", desc.get("MultiSignReserve", ""))


if __name__ == "__main__":
    unittest.main()
