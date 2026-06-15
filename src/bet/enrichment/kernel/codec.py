# ruff: noqa: UP046, UP047
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


def _validate_aware_datetime(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"Expected datetime, got {type(value)}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")


def _decimal_to_plain_string(d: Decimal) -> str:
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Decimal NaN or Infinity are not supported: {d}")
    if d.is_zero():
        return "0"

    sign, digits, exponent = d.as_tuple()
    digits_str = "".join(map(str, digits))

    if exponent >= 0:
        result = digits_str + "0" * exponent
    else:
        abs_exp = abs(exponent)
        if len(digits_str) > abs_exp:
            insert_pos = len(digits_str) - abs_exp
            result = digits_str[:insert_pos] + "." + digits_str[insert_pos:]
        else:
            result = "0." + "0" * (abs_exp - len(digits_str)) + digits_str

    if "." in result:
        result = result.rstrip("0")
        if result.endswith("."):
            result = result[:-1]

    if sign == 1:
        result = "-" + result

    return result


def to_primitive(value: object) -> object:
    if isinstance(value, float):
        raise TypeError(f"Float values are not supported: {value}")
    if isinstance(value, (bytes, bytearray, set, frozenset)):
        raise TypeError(f"Unsupported type: {type(value)}")
    if isinstance(value, bool):
        return value
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return _decimal_to_plain_string(value)
    if isinstance(value, datetime):
        _validate_aware_datetime(value)
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    if isinstance(value, Mapping):
        for k in value.keys():
            if type(k) is not str:
                raise TypeError(f"Mapping keys must be exactly str, got {type(k)}")
        return {k: to_primitive(v) for k, v in sorted(value.items())}
    raise TypeError(f"Unsupported type for serialization: {type(value)}")


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
                    raise TypeError(f"Cannot convert '{value}' to Decimal")
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
                        f"Cannot convert '{value}' to timezone-aware datetime: "
                        "naive datetime is not allowed"
                    )
                return dt.astimezone(UTC)
            except ValueError as e:
                raise TypeError(
                    f"Cannot convert '{value}' to timezone-aware datetime: {e}"
                )
        raise TypeError(f"Expected str for datetime, got {type(value)}")

    if isinstance(base_type, type) and issubclass(base_type, StrEnum):
        if isinstance(value, str):
            try:
                return base_type(value)
            except ValueError:
                raise TypeError(
                    f"Unknown enum value '{value}' for {base_type.__name__}"
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
        except Exception:
            type_hints = {f.name: f.type for f in fields(base_type)}

        processed_data = {}
        for field_info in fields(base_type):
            field_name = field_info.name
            field_type = type_hints.get(field_name, field_info.type)

            if field_name not in value:
                if (
                    field_info.default is MISSING
                    and field_info.default_factory is MISSING
                ):
                    raise ValueError(
                        f"Missing required field '{field_name}' "
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
                            f"'{field_info.default}', got '{field_value}'"
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
