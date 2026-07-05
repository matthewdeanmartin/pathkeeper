# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.4] - 2026-05-19

### Added

- Support `--var` flag for targeting variables other than PATH for test and dry run scenarios

## [0.1.3] - 2026-03-29

### Added

- Locate command to find commands that should be on the path but aren't

## [0.1.2] - 2026-03-25

### Added

- Split long feature for splitting up a PATH that is too long into 2 variables
- Baseline populate for rare case of losing common OS folders

### Fixed

- Windows schedule installer works without admin rights
- False report of "Unresolvable variables for SYSTEMROOT"
- Callback races in tkinter gui

## [0.1.1] - 2026-03-24

### Added

- Application created

[0.1.1]: https://github.com/matthewdeanmartin/pathkeeper/releases/tag/v0.1.1
[0.1.2]: https://github.com/matthewdeanmartin/pathkeeper/compare/v0.1.1...v0.1.2
[0.1.3]: https://github.com/matthewdeanmartin/pathkeeper/compare/v0.1.2...v0.1.3
[0.1.4]: https://github.com/matthewdeanmartin/pathkeeper/compare/v0.1.3...v0.1.4
