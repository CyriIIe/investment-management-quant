"""Tests sans réseau du parsing des réponses MOEX ISS."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from collector import parse_ofz_pd_payload


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "tqob_securities_sample.json"


class CollectorParsingTest(unittest.TestCase):
    def test_parses_only_ofz_pd_and_maps_observed_market_fields(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        bonds, snapshots = parse_ofz_pd_payload(payload, "2026-09-16T14:22:00+00:00")

        self.assertEqual(len(bonds), 1)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(bonds[0].secid, "SU26207RMFS9")
        self.assertEqual(bonds[0].isin, "RU000A0JS3W6")
        self.assertEqual(bonds[0].bond_type, "OFZ-PD")
        self.assertEqual(bonds[0].date_maturite, "2027-02-03")
        self.assertEqual(bonds[0].taux_coupon, 8.15)

        snapshot = snapshots[0]
        self.assertEqual(snapshot.timestamp, "2026-09-16T14:22:00+00:00")
        self.assertEqual(snapshot.prix, 98.29)
        self.assertEqual(snapshot.rendement, 13.2439)
        self.assertEqual(snapshot.duration, 138)
        self.assertEqual(snapshot.date_derniere_transaction, "2026-09-16 14:07:50")
        self.assertEqual(snapshot.volume, 21980)
        self.assertEqual(snapshot.nb_transactions, 312)
        self.assertEqual(snapshot.bid, 98.251)
        self.assertEqual(snapshot.ask, 98.29)


if __name__ == "__main__":
    unittest.main()
