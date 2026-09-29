"""Small counterexamples to ensure P1/P2 are not tautologies."""

import tempfile
import unittest
from pathlib import Path

from run_mcrl2 import verify_snapshot


class VerificationPropertyTests(unittest.TestCase):
    def check(self, spec, property_name, formula):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "tiny.mcrl2"
            model.write_text(spec, encoding="utf-8")
            (root / f"{property_name}.mcf").write_text(formula, encoding="utf-8")
            verdict, _ = verify_snapshot(str(model), property_name, directory)
            return verdict

    def test_p1_detects_second_grant_before_free(self):
        formula = "[true* . grant_A_B . (!free_A_B)* . grant_A_B] false\n"
        self.assertIs(
            self.check("act grant_A_B, free_A_B; init grant_A_B . grant_A_B;\n",
                       "mutual_exclusion", formula), False)
        self.assertIs(
            self.check("act grant_A_B, free_A_B; "
                       "init grant_A_B . free_A_B . grant_A_B;\n",
                       "mutual_exclusion", formula), True)

    def test_p2_detects_premature_deadlock(self):
        formula = ("nu X(c: Nat = 0). ((val(c == 1) || <true>true) && "
                   "[finish] X(c + 1) && [!finish] X(c))\n")
        self.assertIs(self.check("act finish; init delta;\n",
                                 "deadlock_freedom", formula), False)
        self.assertIs(self.check("act finish; init finish;\n",
                                 "deadlock_freedom", formula), True)


if __name__ == "__main__":
    unittest.main()
