# ruff: noqa: UP046, UP047
from __future__ import annotations
import collections.abc
import json
import types
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from datetime import UTC, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Any, TypeVar, Union, get_args, get_origin

T = TypeVar("T")

class DuplicateKeyError(ValueError): pass
class NonFiniteJsonNumberError(ValueError): pass
class StrictJsonTypeError(TypeError): pass
class CanonicalTypeError(TypeError): pass

def _validate_aware_datetime(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"Expected datetime, got {type(value)}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")

def _dec(v: Decimal) -> str:
    if not v.is_finite():
        raise ValueError("Decimal NaN or Infinity are not supported")
    if v.is_zero():
        return "0"
    s = format(v, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s

def to_primitive(v: Any) -> Any:
    if isinstance(v, type):
        raise TypeError("cannot serialize class")
    if isinstance(v, float):
        raise TypeError(f"Float values are not supported: {v}")
    if v is None:
        return None
    if type(v) is bool:
        return v
    if type(v) is int:
        return v
    if type(v) is str:
        return v
    if isinstance(v, StrEnum):
        if not isinstance(v, type):
            if type(v.value) is not str:
                raise TypeError("StrEnum value must be exact str")
            if v.value not in [e.value for e in type(v)]:
                raise TypeError("invalid StrEnum value")
            return v.value
    if type(v) is Decimal:
        return _dec(v)
    if type(v) is datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if is_dataclass(v):
        p = getattr(type(v), "__dataclass_params__", None)
        if p is None or not p.frozen:
            raise TypeError("mutable dataclass is not supported")
        return {f.name: to_primitive(getattr(v, f.name)) for f in fields(v)}
    if type(v) in (list, tuple):
        return [to_primitive(x) for x in v]
    if isinstance(v, Mapping):
        if type(v) is not dict and not isinstance(v, types.MappingProxyType):
            raise TypeError("subclassed mapping is not supported")
        out = {}
        for k, x in v.items():
            if type(k) is not str:
                raise TypeError("Mapping keys must be exactly str")
            out[k] = to_primitive(x)
        return out
    raise TypeError(f"Unsupported type: {type(v)}")

def canonical_json_bytes(value: object) -> bytes:
    primitive = to_primitive(value)
    return json.dumps(
        primitive,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

def canonical_json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")

def canonical_sha256(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()

def _pairs(items):
    out = {}
    for key, value in items:
        if type(key) is not str:
            raise StrictJsonTypeError("object key must be exact str")
        if key in out:
            raise DuplicateKeyError(f"Duplicate key: {key}")
        out[key] = value
    return out

def _constant(value):
    raise NonFiniteJsonNumberError(f"Non-finite JSON number: {value}")

def _validate_no_surrogates(v: Any) -> None:
    if type(v) is str:
        if any(0xD800 <= ord(c) <= 0xDFFF for c in v):
            raise ValueError("Unpaired Unicode surrogate found")
    elif type(v) is list:
        for x in v:
            _validate_no_surrogates(x)
    elif type(v) is dict:
        for k, x in v.items():
            _validate_no_surrogates(k)
            _validate_no_surrogates(x)

def loads_strict(data: str | bytes) -> Any:
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("Invalid UTF-8 bytes") from exc
    elif type(data) is not str:
        raise StrictJsonTypeError(f"Expected str or bytes, got {type(data).__name__}")

    if any(0xD800 <= ord(c) <= 0xDFFF for c in data):
        raise ValueError("Unpaired Unicode surrogate found in string")

    res = json.loads(
        data,
        object_pairs_hook=_pairs,
        parse_float=Decimal,
        parse_int=int,
        parse_constant=_constant
    )
    _validate_no_surrogates(res)
    return res

def _validate_fail_closed_value(value: object) -> None:
    if isinstance(value, float):
        raise TypeError(f"Float values are not allowed: {value}")
    if isinstance(value, (bytes, bytearray, set, frozenset)):
        raise TypeError(f"Bytes and sets are not allowed: {type(value)}")
    if value is None or isinstance(value, (bool, int, str, Decimal, datetime)):
        if isinstance(value, bool):
            return
        if isinstance(value, int) and not isinstance(value, bool):
            return
        if isinstance(value, str):
            return
        if isinstance(value, Decimal):
            if value.is_nan() or value.is_infinite():
                raise TypeError("NaN/Infinity Decimals are not allowed")
            return
        if isinstance(value, datetime):
            _validate_aware_datetime(value)
            return
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_fail_closed_value(item)
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            if type(k) is not str:
                raise TypeError(
                    "Only string keys are allowed in mappings "
                    f"under Any/object, got {type(k)}"
                )
            _validate_fail_closed_value(v)
        return
    raise TypeError(f"Unsupported object type in fail-closed decode: {type(value)}")

def _from_primitive_impl(
    expected_type: type[T], value: object, type_map: dict = None
) -> T:
    if expected_type is Any or expected_type is object:
        _validate_fail_closed_value(value)
        return value

    if isinstance(expected_type, TypeVar):
        if type_map and expected_type in type_map:
            expected_type = type_map[expected_type]
            if expected_type is Any or expected_type is object:
                _validate_fail_closed_value(value)
                return value
        else:
            raise TypeError(f"Unresolved TypeVar: {expected_type}")

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin is not None and not isinstance(origin, str):
        type_vars = getattr(origin, "__parameters__", ())
        if isinstance(type_vars, tuple) and type_vars and args:
            current_map = dict(zip(type_vars, args))
            if type_map:
                resolved_map = {}
                for tv, t in current_map.items():
                    if isinstance(t, TypeVar) and t in type_map:
                        resolved_map[tv] = type_map[t]
                    else:
                        resolved_map[tv] = t
                type_map = resolved_map
            else:
                type_map = current_map

    union_types = (Union,)
    if hasattr(types, "UnionType"):
        union_types += (types.UnionType,)

    if origin in union_types:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(args) != 2 or len(non_none_args) != 1:
            raise TypeError(f"Arbitrary Union is not supported: {expected_type}")
        if value is None:
            return None
        try:
            return _from_primitive_impl(non_none_args[0], value, type_map)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Could not convert {value} to any of {expected_type}: {e}")

    if origin is list:
        if not isinstance(value, list):
            raise TypeError(f"Expected list, got {type(value)}")
        item_type = args[0] if args else Any
        return [_from_primitive_impl(item_type, item, type_map) for item in value]

    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise TypeError(f"Expected tuple or list, got {type(value)}")
        if not args:
            return tuple(_from_primitive_impl(Any, item, type_map) for item in value)
        if len(args) == 2 and args[1] is Ellipsis:
            item_type = args[0]
            return tuple(
                _from_primitive_impl(item_type, item, type_map) for item in value
            )
        elif len(args) == len(value):
            return tuple(
                _from_primitive_impl(arg_type, item, type_map)
                for arg_type, item in zip(args, value)
            )
        else:
            raise ValueError(
                f"Tuple length mismatch: expected {len(args)}, got {len(value)}"
            )

    if origin in (dict, collections.abc.Mapping, Mapping):
        if not isinstance(value, Mapping):
            raise TypeError(f"Expected mapping, got {type(value)}")
        key_type = args[0] if args else str
        value_type = args[1] if len(args) > 1 else Any
        if key_type is not str:
            raise TypeError(
                f"Only string keys are supported for mappings, got {key_type}"
            )
        for k in value.keys():
            if type(k) is not str:
                raise TypeError(
                    "Only string keys are supported for mappings, "
                    f"got key of type {type(k)}"
                )
        return {
            _from_primitive_impl(key_type, k, type_map): _from_primitive_impl(
                value_type, v, type_map
            )
            for k, v in value.items()
        }

    base_type = origin if origin is not None else expected_type

    if origin is not None:
        if (
            origin not in (list, tuple, dict, collections.abc.Mapping, Mapping, Union)
            and not (hasattr(types, "UnionType") and origin is types.UnionType)
            and not is_dataclass(origin)
        ):
            raise TypeError(f"Unsupported typing construct: {expected_type}")
    else:
        if not (
            base_type is Any
            or base_type is object
            or base_type is type(None)
            or base_type is bool
            or base_type is int
            or base_type is str
            or base_type is Decimal
            or base_type is datetime
            or (isinstance(base_type, type) and issubclass(base_type, StrEnum))
            or is_dataclass(base_type)
        ):
            raise TypeError(f"Unsupported expected type: {expected_type}")

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
                d = Decimal(value) if isinstance(value, str) else value
                if d.is_nan() or d.is_infinite():
                    raise TypeError(f"Cannot convert \x27{value}\x27 to Decimal")
                return d
            except InvalidOperation:
                raise TypeError(f"Cannot convert {value} to Decimal")
        raise TypeError(f"Expected Decimal (str or Decimal), got {type(value)}")

    if base_type is datetime:
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None or dt.utcoffset() is None:
                    raise TypeError(
                        f"Cannot convert \x27{value}\x27 to timezone-aware datetime: "
                        "naive datetime is not allowed"
                    )
                return dt.astimezone(UTC)
            except ValueError as e:
                raise TypeError(
                    f"Cannot convert \x27{value}\x27 to timezone-aware datetime: {e}"
                )
        raise TypeError(f"Expected str for datetime, got {type(value)}")

    if isinstance(base_type, type) and issubclass(base_type, StrEnum):
        if isinstance(value, str):
            try:
                return base_type(value)
            except ValueError:
                raise TypeError(
                    f"Unknown enum value \x27{value}\x27 for {base_type.__name__}"
                )
        raise TypeError(f"Expected str for StrEnum, got {type(value)}")

    if is_dataclass(base_type):
        if not isinstance(value, Mapping):
            raise TypeError(
                f"Expected mapping for dataclass {base_type.__name__}, "
                f"got {type(value)}"
            )

        params = getattr(base_type, "__dataclass_params__", None)
        if params is None or not params.frozen:
            raise TypeError(f"Dataclass {base_type.__name__} must be frozen")

        from typing import get_type_hints

        try:
            type_hints = get_type_hints(base_type)
        except Exception as exc:
            raise TypeError(
                f"Could not resolve type hints for dataclass {base_type.__name__}"
            ) from exc

        processed_data = {}
        for field_info in fields(base_type):
            field_name = field_info.name
            field_type = type_hints.get(field_name, field_info.type)

            if field_name not in value:
                if field_name == "schema_version":
                    raise ValueError(
                        f"Missing required field \x27schema_version\x27 "
                        f"for dataclass {base_type.__name__}"
                    )
                if (
                    field_info.default is MISSING
                    and field_info.default_factory is MISSING
                ):
                    raise ValueError(
                        f"Missing required field \x27{field_name}\x27 "
                        f"for dataclass {base_type.__name__}"
                    )
                continue

            field_value = value[field_name]

            if field_name == "schema_version":
                if field_info.default is not MISSING and isinstance(
                    field_info.default, str
                ):
                    if field_value != field_info.default:
                        raise ValueError(
                            f"schema_version mismatch: expected "
                            f"\x27{field_info.default}\x27, got \x27{field_value}\x27"
                        )

            processed_data[field_name] = _from_primitive_impl(
                field_type, field_value, type_map
            )

        unknown_fields = set(value.keys()) - set(f.name for f in fields(base_type))
        if unknown_fields:
            raise ValueError(
                f"Unknown fields {unknown_fields} for dataclass {base_type.__name__}"
            )

        return base_type(**processed_data)

    raise TypeError(f"Unsupported expected type: {expected_type}")

def from_primitive(expected_type: type[T], value: object) -> T:
    return _from_primitive_impl(expected_type, value)
