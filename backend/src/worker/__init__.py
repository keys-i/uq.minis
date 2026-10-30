"""Persistent mailbox worker storage, transports and lifecycle

Storage, mailbox transports and event progression live in separate modules
Importing this package starts no polling, sign-in, scheduled job or network
activity; commands choose those effects explicitly
"""
