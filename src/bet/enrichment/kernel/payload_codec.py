from __future__ import annotations
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")
CodecIdentity = tuple[str, int]

class DuplicateCodecRegistrationError(ValueError): pass
class CodecRegistryFrozenError(RuntimeError): pass
class UnknownPayloadCodecError(KeyError): pass
class InvalidPayloadCodecError(TypeError): pass

class PayloadCodec(Protocol, Generic[T]):
    capability_key: str
    schema_version: int
    dto_type: type[T]
    def encode(self, value: T) -> Mapping[str, object]: ...
    def decode(self, payload: Mapping[str, object]) -> T: ...

class PayloadCodecRegistry:
    def __init__(self) -> None:
        self._codecs: dict[CodecIdentity, PayloadCodec[Any]] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register(self, codec: PayloadCodec[Any]) -> None:
        if self._frozen:
            raise CodecRegistryFrozenError("Registry is frozen")
        if type(codec.capability_key) is not str or not codec.capability_key:
            raise InvalidPayloadCodecError("capability_key must be a non-empty string")
        if type(codec.schema_version) is not int or codec.schema_version < 1:
            raise InvalidPayloadCodecError("schema_version must be an integer >= 1")
        if not isinstance(codec.dto_type, type):
            raise InvalidPayloadCodecError("dto_type must be a concrete type")
        identity = (codec.capability_key, codec.schema_version)
        if identity in self._codecs:
            raise DuplicateCodecRegistrationError(f"Duplicate registration: {identity}")
        self._codecs[identity] = codec

    def freeze(self) -> None:
        self._frozen = True

    def get(self, key: str, version: int) -> PayloadCodec[Any]:
        if type(key) is not str or type(version) is not int:
            raise UnknownPayloadCodecError((key, version))
        identity = (key, version)
        if identity not in self._codecs:
            raise UnknownPayloadCodecError(identity)
        return self._codecs[identity]

    def identities(self) -> tuple[CodecIdentity, ...]:
        return tuple(sorted(self._codecs.keys()))

    def snapshot(self) -> Mapping[CodecIdentity, PayloadCodec[Any]]:
        return MappingProxyType(dict(self._codecs))
