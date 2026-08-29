"""Request / commit helpers for StateService.

Kept next to StateService so the lock-queue behaviour has a single place
to read. StateService owns the fields; this module only documents the
contract used by PR B.

- requested_key: last intended target (last write wins while locked)
- committed_key: StateCollection.current_key(), what the pet has arrived at
- set_state(): thin wrapper around request_state()
"""
