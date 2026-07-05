
class KhataNotImplementedError(NotImplementedError):
    pass


def extract(engine, image_path: str, threshold: float = None) -> dict:
    raise KhataNotImplementedError(
        f"Khata extraction is not implemented in this pass ({image_path}). "
        "This document type requires Urdu handwriting recognition, which is "
        "explicitly out of scope here — see project notes. Route khata images "
        "to a separate pipeline once that work starts."
    )
