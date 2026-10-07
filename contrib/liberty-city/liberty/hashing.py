"""GTA IV names models by the Jenkins one-at-a-time hash of the lowercase name."""


def model_hash(name: str) -> int:
    h = 0
    for byte in name.lower().encode("ascii"):
        h = (h + byte) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    return (h + (h << 15)) & 0xFFFFFFFF
