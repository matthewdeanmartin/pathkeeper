# Prior art

The original project specification called out a few tools that helped shape `pathkeeper`.

## WindowsPathFix

PowerShell-only and Windows-only. It inspired the idea of scanning for likely tool directories and repairing a damaged PATH automatically.

## PyWinPath

A Python CLI for editing the Windows PATH via the registry. It demonstrates direct registry management, but does not focus on backup history and restore workflows.

## Path Backup & Restore

A Windows GUI tool that exports environment data. It shows that backup and restore are valuable, but its workflow is more manual and less automation-focused.

## Environment.ahk

An AutoHotkey-based Windows utility with backup and cleanup functions. It is useful prior art for sort and dedupe ideas.

## PowerToys Environment Variables

PowerToys provides profile-based environment management and backup when applying profiles, but it is not a dedicated cross-platform PATH repair workflow.

## Where `pathkeeper` differs

`pathkeeper` aims to combine the most useful ideas from these tools:

- cross-platform operation
- local versioned backups
- diagnosis before write
- explicit restore workflows
- automation through scheduled backups
