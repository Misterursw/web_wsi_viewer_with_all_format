from __future__ import annotations


class AslideError(Exception):
    pass


class UnsupportedOperationError(AslideError):
    pass


class UnknownBiomarkerError(AslideError):
    pass


class MissingDefaultBiomarkerError(AslideError):
    pass
