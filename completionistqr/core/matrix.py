"""QR-Encoder: Payload -> boolesche Modulmatrix (ohne Quiet Zone)."""
from __future__ import annotations

from dataclasses import dataclass

import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q

_ECC = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}


@dataclass
class QRMatrix:
    modules: list[list[bool]]
    version: int

    @property
    def size(self) -> int:
        return len(self.modules)

    def finder_origins(self) -> list[tuple[int, int]]:
        """Obere linke Ecken (x, y) der drei 7x7-Finder-Patterns."""
        n = self.size
        return [(0, 0), (n - 7, 0), (0, n - 7)]

    def in_finder(self, x: int, y: int) -> bool:
        n = self.size
        return (x < 7 and y < 7) or (x >= n - 7 and y < 7) or (x < 7 and y >= n - 7)

    def dark(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size and self.modules[y][x]


def build(payload: str, ecc: str = "H") -> QRMatrix:
    qr = qrcode.QRCode(error_correction=_ECC.get(ecc, ERROR_CORRECT_H), border=0)
    qr.add_data(payload or " ")
    qr.make(fit=True)
    return QRMatrix(modules=[list(row) for row in qr.get_matrix()], version=qr.version)
