import unittest

from baseline_check import DELTA_T_SEP, compute_baseline_cost, train_intervals
from extract_data import load_corridor_trains, select_density_subset, tag_fastest_as_premium


class BaselineTests(unittest.TestCase):
    def test_greedy_schedule_has_no_overlapping_blocks(self):
        trains = load_corridor_trains()
        for n in (5, 12):
            with self.subTest(n=n):
                subset = select_density_subset(trains, n)
                tag_fastest_as_premium(subset)
                cost, delays = compute_baseline_cost(subset)
                self.assertEqual(cost, sum(
                    train.priority_weight * delays[train_id]
                    for train_id, train in subset.items()
                ))
                occupations = {}
                for train_id, train in subset.items():
                    for block, start, end in train_intervals(train):
                        occupations.setdefault(block, []).append(
                            (start + delays[train_id], end + delays[train_id])
                        )
                for intervals in occupations.values():
                    ordered = sorted(intervals)
                    for first, second in zip(ordered, ordered[1:]):
                        self.assertGreaterEqual(second[0], first[1] + DELTA_T_SEP)


if __name__ == "__main__":
    unittest.main()
