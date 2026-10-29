from typing import Dict, Optional, Union, Any, List


class PromptIdMapper:
    """
    Bidirectional mapping between internal string database identifiers
    (MongoDB _ids, UUIDs) and 1-based sequential integer indices used in LLM prompts.

    Eliminates character-level hallucination and context bloat by letting the LLM
    work exclusively with compact integers while the orchestrator / database
    engine retains canonical database IDs.
    """

    def __init__(self, prefix: str = "item"):
        self.prefix = prefix
        self._int_to_id: Dict[int, str] = {}
        self._id_to_int: Dict[str, int] = {}
        self._counter = 1

    def register(self, real_id: str) -> int:
        """Registers a database ID if not already tracked and returns its integer index."""
        if real_id not in self._id_to_int:
            idx = self._counter
            self._counter += 1
            self._int_to_id[idx] = real_id
            self._id_to_int[real_id] = idx
        return self._id_to_int[real_id]

    def register_many(self, real_ids: List[str]) -> List[int]:
        """Registers multiple real IDs and returns the list of assigned integer indices."""
        return [self.register(rid) for rid in real_ids]

    def to_index(self, real_id: str) -> Optional[int]:
        """Returns the prompt integer index for a given database ID, or None if untracked."""
        return self._id_to_int.get(real_id)

    def to_id(self, index: Union[int, str]) -> Optional[str]:
        """
        Translates a prompt integer index back to its internal database ID.
        Robustly coerces string digits ('1', '02') into integers.
        """
        try:
            int_key = int(index)
            return self._int_to_id.get(int_key)
        except (ValueError, TypeError):
            return None

    def dump_map(self) -> Dict[int, str]:
        """Returns a snapshot of the current int -> string ID mapping."""
        return dict(self._int_to_id)

    def __len__(self) -> int:
        return len(self._int_to_id)
