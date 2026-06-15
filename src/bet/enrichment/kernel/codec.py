import collections.abc
import json
import types
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Any, TypeVar, Union, get_args, get_origin

T = TypeVar("T")

def to_primitive(value: object) -> object:
    if value is None or isinstance(value, (int, str, bool)):
        if isinstance(value, bool) and not isinstance(value, int):
            # Python bool is a subclass of int, so we explicitly check for bool
            # to prevent it from being treated as an int ID where it shouldn't
            raise TypeError(f"Unsupported primitive type: {type(value)}")
        return value
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            raise ValueError(f"Decimal NaN or Infinity are not supported: {value}")
        # Normalize Decimal to a string without redundant trailing zeros and handle negative zero
        normalized_decimal_str = str(value.normalize())
        if normalized_decimal_str == "-0":
            return "0"
        return normalized_decimal_str
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Naive datetime is not supported")
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    if isinstance(value, Mapping):
        # Ensure all keys are strings and sort them for deterministic output
        return {
            str(k): to_primitive(v)
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
        }

    # Reject floats and other unsupported types explicitly
    if isinstance(value, float):
        raise TypeError(f"Float values are not supported: {value}")

    raise TypeError(f"Unsupported type for serialization: {type(value)}")

def canonical_json_bytes(value: object) -> bytes:
    primitive = to_primitive(value)
    # Use custom separators and ensure_ascii=False for canonical form
    return json.dumps(
        primitive, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')

def canonical_json_text(value: object) -> str:
    return canonical_json_bytes(value).decode('utf-8')

def canonical_sha256(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()

def from_primitive(expected_type: type[T], value: object, _type_map: dict = None) -> T:
    if expected_type is Any or expected_type is object:
        return value

    if isinstance(expected_type, TypeVar):
        if _type_map and expected_type in _type_map:
            expected_type = _type_map[expected_type]
            if expected_type is Any or expected_type is object:
                return value
        else:
            return value

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    # Setup type map for generic dataclasses
    if origin is not None and not isinstance(origin, str):
        type_vars = getattr(origin, "__parameters__", ())
        if isinstance(type_vars, tuple) and type_vars and args:
            current_map = dict(zip(type_vars, args))
            if _type_map:
                # Merge and resolve inherited type variables
                resolved_map = {}
                for tv, t in current_map.items():
                    if isinstance(t, TypeVar) and t in _type_map:
                        resolved_map[tv] = _type_map[t]
                    else:
                        resolved_map[tv] = t
                _type_map = resolved_map
            else:
                _type_map = current_map

    # Check container origins
    union_types = (Union,)
    if hasattr(types, "UnionType"):
        union_types += (types.UnionType,)

    if origin in union_types:
        if value is None:
            return None
        non_none_args = [arg for arg in args if arg is not type(None)]
        for arg in non_none_args:
            try:
                return from_primitive(arg, value, _type_map)
            except (TypeError, ValueError):
                pass
        raise TypeError(f"Could not convert {value} to any of {expected_type}")

    if origin is list:
        if not isinstance(value, list):
            raise TypeError(f"Expected list, got {type(value)}")
        item_type = args[0] if args else Any
        return [from_primitive(item_type, item, _type_map) for item in value]

    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise TypeError(f"Expected tuple or list, got {type(value)}")
        if not args:
            return tuple(from_primitive(Any, item, _type_map) for item in value)
        if len(args) == 2 and args[1] is Ellipsis:
            item_type = args[0]
            return tuple(from_primitive(item_type, item, _type_map) for item in value)
        elif len(args) == len(value):
            return tuple(from_primitive(arg_type, item, _type_map) for arg_type, item in zip(args, value))
        else:
            raise ValueError(f"Tuple length mismatch: expected {len(args)}, got {len(value)}")

    if origin in (dict, collections.abc.Mapping, Mapping):
        if not isinstance(value, Mapping):
            raise TypeError(f"Expected mapping, got {type(value)}")
        key_type = args[0] if args else str
        value_type = args[1] if len(args) > 1 else Any
        if key_type is not str:
            raise TypeError(f"Only string keys are supported for mappings, got {key_type}")
        return {
            from_primitive(key_type, k, _type_map): from_primitive(value_type, v, _type_map)
            for k, v in value.items()
        }

    # Now we handle base type (non-generic/unwrapped or origin)
    base_type = origin if origin is not None else expected_type

    if base_type is type(None):
        if value is None:
            return None
        raise TypeError(f"Expected None, got {type(value)}")

    if base_type is bool:
        if isinstance(value, bool):
            return value
        raise TypeError(f"Expected bool, got {type(value)}")

    if base_type is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise TypeError(f"Expected int, got {type(value)}")

    if base_type is str:
        if isinstance(value, str):
            return value
        raise TypeError(f"Expected str, got {type(value)}")

    if base_type is Decimal:
        if isinstance(value, (str, Decimal)):
            try:
                d = Decimal(value)
                if d.is_nan() or d.is_infinite():
                    raise TypeError(f"Cannot convert '{value}' to Decimal")
                return d.normalize()
            except InvalidOperation:
                raise TypeError(f"Cannot convert {value} to Decimal")
        raise TypeError(f"Expected Decimal (str or Decimal), got {type(value)}")

    if base_type is datetime:
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    raise ValueError("Naive datetime is not supported")
                return dt
            except ValueError as e:
                raise TypeError(f"Cannot convert '{value}' to timezone-aware datetime: {e}")
        raise TypeError(f"Expected str for datetime, got {type(value)}")

    if isinstance(base_type, type) and issubclass(base_type, StrEnum):
        if isinstance(value, str):
            try:
                return base_type(value)
            except ValueError:
                raise TypeError(f"Unknown enum value '{value}' for {base_type.__name__}")
        raise TypeError(f"Expected str for StrEnum, got {type(value)}")

    if is_dataclass(base_type):
        if not isinstance(value, Mapping):
            raise TypeError(f"Expected mapping for dataclass {base_type.__name__}, got {type(value)}")

        processed_data = {}
        for field_info in fields(base_type):
            field_name = field_info.name
            field_type = field_info.type

            if field_name not in value:
                if field_info.default is MISSING and field_info.default_factory is MISSING:
                    raise ValueError(f"Missing required field '{field_name}' for dataclass {base_type.__name__}")
                continue

            field_value = value[field_name]
            processed_data[field_name] = from_primitive(field_type, field_value, _type_map)

        # Check for unknown fields
        unknown_fields = set(value.keys()) - set(f.name for f in fields(base_type))
        if unknown_fields:
            raise ValueError(f"Unknown fields {unknown_fields} for dataclass {base_type.__name__}")

        return base_type(**processed_data)

    raise TypeError(f"Unsupported expected type: {expected_type}")
