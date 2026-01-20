import math
from typing import Any, List, Dict, Union, Optional, Callable


# --- DataUtils Class ---

class DataUtils:
    """
    A utility class providing common data manipulation and comparison functions.
    """

    def _recursive_compare(self, a: Any, b: Any, path: str, include: Optional[List[str]], exclude: Optional[List[str]],
                           differences: List[Dict[str, Any]]) -> None:
        """
        Recursively compares two objects (dicts, lists, or primitives) for full equality.
        """
        current_path = path if path else 'root'

        if exclude and any(current_path.startswith(e) for e in exclude):
            return

        if include:
            is_included = False
            for i in include:
                if current_path.startswith(i) or i.startswith(current_path) or current_path == 'root':
                    is_included = True
                    break
            if not is_included and current_path != 'root':
                return

        if type(a) != type(b):
            differences.append({'path': current_path, 'type': 'Type Difference',
                                'details': f"Types differ: {type(a).__name__} vs {type(b).__name__}"})
            return

        if isinstance(a, dict):
            keys_a = set(a.keys())
            keys_b = set(b.keys())

            for key in keys_a - keys_b:
                differences.append({'path': f"{current_path}.{key}", 'type': 'Missing Key',
                                    'details': f"Key '{key}' exists in A but not B"})

            for key in keys_b - keys_a:
                differences.append({'path': f"{current_path}.{key}", 'type': 'Missing Key',
                                    'details': f"Key '{key}' exists in B but not A"})

            for key in keys_a & keys_b:
                self._recursive_compare(a[key], b[key], f"{current_path}.{key}", include, exclude, differences)

        elif isinstance(a, (list, tuple)):
            if len(a) != len(b):
                differences.append({'path': current_path, 'type': 'Length Difference',
                                    'details': f"Lengths differ: {len(a)} vs {len(b)}"})

            min_len = min(len(a), len(b))
            for i in range(min_len):
                self._recursive_compare(a[i], b[i], f"{current_path}[{i}]", include, exclude, differences)

            if len(a) > len(b):
                differences.append({'path': f"{current_path}[{min_len}]", 'type': 'Extra Element',
                                    'details': f"Element exists in A but not B at index {min_len}"})
            elif len(b) > len(a):
                differences.append({'path': f"{current_path}[{min_len}]", 'type': 'Extra Element',
                                    'details': f"Element exists in B but not A at index {min_len}"})

        elif a != b:
            differences.append(
                {'path': current_path, 'type': 'Value Difference', 'details': f"Values differ: '{a}' vs '{b}'"})

    def compare_objects(self, obj1: Any, obj2: Any, include: Optional[List[str]] = None,
                        exclude: Optional[List[str]] = None) -> Dict[str, Union[bool, List[Dict[str, Any]]]]:
        """
        Compares two arbitrary Python objects (dicts, lists, primitives) recursively.
        """
        differences: List[Dict[str, Any]] = []

        if include:
            include = [p.lstrip('.') for p in include if not p.startswith('root')]
        if exclude:
            exclude = [p.lstrip('.') for p in exclude if not p.startswith('root')]

        self._recursive_compare(obj1, obj2, "", include, exclude, differences)

        return {
            'is_equal': len(differences) == 0,
            'differences': differences
        }

    def is_subset(self, subset: Any, superset: Any) -> bool:
        """
        Checks if the 'subset' object is entirely contained within the 'superset' object.

        Rules:
        1. Primitives: Must be equal (subset == superset).
        2. Dictionaries: All keys/values in the subset must exist and match in the superset.
           (Superset can have extra keys).
        3. Lists/Tuples: The superset must contain the subset's elements, in order, up to
           the length of the subset. (Superset can be longer).

        Args:
            subset (Any): The object that should be contained (e.g., a query object).
            superset (Any): The object that should contain the subset.

        Returns:
            bool: True if subset is included in superset, False otherwise.
        """
        if type(subset) != type(superset):
            return False

        # 1. Primitives
        if not isinstance(subset, (dict, list, tuple)):
            return subset == superset

        # 2. Dictionaries
        if isinstance(subset, dict):
            for key, sub_value in subset.items():
                if key not in superset:
                    return False
                if not self.is_subset(sub_value, superset[key]):
                    return False
            return True

        # 3. Lists/Tuples (Strict ordered subset check)
        if isinstance(subset, (list, tuple)):
            # Superset must be at least as long
            if len(subset) > len(superset):
                return False

            # Check element by element up to the length of the subset
            for i in range(len(subset)):
                if not self.is_subset(subset[i], superset[i]):
                    return False
            return True

        # Should be unreachable if types are handled above, but as a fallback
        return subset == superset

    def round_value(self, value: Union[int, float], precision: int = 2) -> Union[int, float]:
        """
        Rounds a float or returns an integer if passed one.
        """
        if isinstance(value, int):
            return value

        return round(value, precision)

    def convert_to_type(self, value: Any, target_type: Union[type, str]) -> Any:
        """
        Converts a value to a specified target type.
        """
        type_map = {
            'int': int,
            'float': float,
            'str': str,
            'bool': bool
        }

        if isinstance(target_type, str):
            target_type = type_map.get(target_type.lower(), str)

        try:
            if target_type is bool:
                if isinstance(value, str):
                    s_val = value.lower().strip()
                    return s_val in ('true', '1', 't', 'y', 'yes')
                if isinstance(value, (int, float)):
                    return value != 0
                return bool(value)

            return target_type(value)
        except (ValueError, TypeError):
            return value


