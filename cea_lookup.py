"""Persistent, checked bilinear lookup for MATLAB CEA2 raw outputs.

Interpolation is accepted only after a direct CEA check within each cell.
Any failed cell remains direct-only until a new model/configuration namespace.
"""

import hashlib
import io
import math
import sqlite3
import time
from pathlib import Path

import cea_lookup_config as cfg

DEFAULT_DB = Path(__file__).resolve().parent / "user_settings" / "cea_lookup.sqlite3"
_SOURCE_FINGERPRINT = None


class CeaLookup:
    def __init__(self, matlab_engine, fuel_id, ox_id, *, mode=None, db_path=DEFAULT_DB):
        self.eng = matlab_engine
        self.mode = cfg.MODE if mode is None else mode
        if self.mode not in ("lookup", "direct"):
            raise ValueError("CEA mode must be 'lookup' or 'direct'")
        self.db_path = Path(db_path)
        self.conn = None
        self.namespace = None
        self.fuel_id, self.ox_id = fuel_id, ox_id
        self.stats = dict(direct_calls=0, grid_nodes=0, interpolations=0,
                          verified_cells=0, failed_cells=0, direct_seconds=0.0,
                          lookup_seconds=0.0)
        self._cell_hits = {}

    def _namespace(self):
        if self.namespace is None:
            global _SOURCE_FINGERPRINT
            if _SOURCE_FINGERPRINT is None:
                source = ""
                try:
                    source = str(self.eng.which("CEA2", nargout=1))
                except Exception:
                    pass  # Fall back to the explicit user-controlled model tag.
                path = Path(source)
                _SOURCE_FINGERPRINT = (
                    hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else source
                )
            description = (cfg.CEA_MODEL_TAG, _SOURCE_FINGERPRINT, self.fuel_id, self.ox_id,
                           cfg.PRESSURE_STEP_PSIA, cfg.OF_STEP, cfg.MAX_RELATIVE_ERROR)
            self.namespace = hashlib.sha256(repr(description).encode()).hexdigest()
        return self.namespace

    def _db(self):
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, timeout=30)
            self.conn.execute("CREATE TABLE IF NOT EXISTS nodes (ns TEXT, pi INTEGER, oi INTEGER, data TEXT, PRIMARY KEY(ns, pi, oi))")
            self.conn.execute("CREATE TABLE IF NOT EXISTS cells (ns TEXT, pi INTEGER, oi INTEGER, good INTEGER, PRIMARY KEY(ns, pi, oi))")
        return self.conn

    def _direct(self, pressure, of):
        start = time.perf_counter()
        output = io.StringIO()
        try:
            raw = self.eng.CEA2(float(pressure), float(of), nargout=4, stdout=output, stderr=output)
            values = tuple(float(x) for x in raw)
            if len(values) != 4 or not all(math.isfinite(v) and v > 0 for v in values):
                raise ValueError("CEA2 returned non-finite or non-positive properties")
            return values
        finally:
            output.close()
            self.stats["direct_calls"] += 1
            self.stats["direct_seconds"] += time.perf_counter() - start

    def _node(self, pi, oi):
        db = self._db()
        ns = self._namespace()
        row = db.execute("SELECT data FROM nodes WHERE ns=? AND pi=? AND oi=?", (ns, pi, oi)).fetchone()
        if row:
            return tuple(float(x) for x in row[0].split(","))
        point = self._direct(pi * cfg.PRESSURE_STEP_PSIA, oi * cfg.OF_STEP)
        db.execute("INSERT OR IGNORE INTO nodes VALUES (?, ?, ?, ?)",
                   (ns, pi, oi, ",".join(format(x, ".17g") for x in point)))
        db.commit()
        self.stats["grid_nodes"] += 1
        return point

    def get(self, pressure_psia, of_ratio):
        if not all(math.isfinite(v) and v > 0 for v in (pressure_psia, of_ratio)):
            raise ValueError("CEA pressure and O/F must be positive finite numbers")
        # Never ask MATLAB for a zero or negative grid-corner input.
        if (self.mode == "direct" or pressure_psia < cfg.PRESSURE_STEP_PSIA
                or of_ratio < cfg.OF_STEP):
            return self._direct(pressure_psia, of_ratio)
        start = time.perf_counter()
        previous_direct = self.stats["direct_seconds"]
        try:
            return self._lookup(pressure_psia, of_ratio)
        finally:
            self.stats["lookup_seconds"] += max(0, time.perf_counter() - start
                                                 - (self.stats["direct_seconds"] - previous_direct))

    def _lookup(self, pressure, of):
        px, ox = pressure / cfg.PRESSURE_STEP_PSIA, of / cfg.OF_STEP
        pi, oi = math.floor(px), math.floor(ox)
        db = self._db()
        ns = self._namespace()
        status = db.execute("SELECT good FROM cells WHERE ns=? AND pi=? AND oi=?",
                            (ns, pi, oi)).fetchone()
        if status == (0,):
            return self._direct(pressure, of)
        a, b = px - pi, ox - oi
        corners = (self._node(pi, oi), self._node(pi + 1, oi),
                   self._node(pi, oi + 1), self._node(pi + 1, oi + 1))
        predicted = tuple((1-a)*(1-b)*corners[0][i] + a*(1-b)*corners[1][i]
                          + (1-a)*b*corners[2][i] + a*b*corners[3][i]
                          for i in range(4))
        cell = (pi, oi)
        self._cell_hits[cell] = self._cell_hits.get(cell, 0) + 1
        if status is None or self._cell_hits[cell] % cfg.RECHECK_EVERY == 0:
            actual = self._direct(pressure, of)
            good = all(abs(x-y)/abs(y) <= cfg.MAX_RELATIVE_ERROR
                       for x, y in zip(predicted, actual))
            db.execute("INSERT OR REPLACE INTO cells VALUES (?, ?, ?, ?)",
                       (ns, pi, oi, int(good)))
            db.commit()
            self.stats["verified_cells" if good else "failed_cells"] += 1
            return actual  # Validation always returns exact CEA properties.
        self.stats["interpolations"] += 1
        return predicted

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
