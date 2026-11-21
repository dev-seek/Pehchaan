"""Resolvers turn spans of an utterance into entities. Each owns one kind of decision; the pipeline runs them in order."""
from .base import Resolver
from .memory import JsonMemoryStore, MemoryResolver, MemoryStore, NullMemoryStore
from .names import NameResolver
from .numbers import NumberResolver

__all__ = ["Resolver", "NumberResolver", "MemoryResolver", "MemoryStore", "JsonMemoryStore", "NullMemoryStore",
           "NameResolver"]
