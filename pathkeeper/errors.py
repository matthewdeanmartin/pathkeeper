from __future__ import annotations


class PathkeeperError(Exception):
    exit_code = 1


class InvalidArgumentsError(PathkeeperError):
    exit_code = 2


class PermissionDeniedError(PathkeeperError):
    exit_code = 3


class BackupNotFoundError(PathkeeperError):
    exit_code = 4


class UserCancelledError(PathkeeperError):
    exit_code = 5

