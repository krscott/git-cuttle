# Design Document

This document outlines the design, architecture, and components of the
`git-cuttle` application. It serves as a comprehensive guide for understanding
and reproducing the system's functionality.

## Overview

`git-cuttle` is a Command Line Interface (CLI) application for managing git
multi-branch workflows.

## Design Methodology

In descending order, this project optimizes for:

1. Correctness - ops shall result in a good state
2. Reliability - ops should be reproducable
3. User-friendly - ops should have a minimal interface and useful error messages
4. Speed - ops should be efficient

All requirements listed in this document shall have corresponding integration
tests. Wherever possible, tests should be implemented first (Red-Green-Refactor).

## Architecture

The application is divied into distinct modules

- CLI (`__main__.py`): Handles CLI input
- Orchestrater: Connects other modules
- Git ops: Wraps the git/gh cli tools in python wrapper functions
- Metadata manager: Manages persistent metadata of all managed workspaces

## Persistent Data

All user data is stored in `$XDG_DATA_HOME/gitcuttle/workspaces.json`.

The schema shall be versioned with a `"version": int` key.

This data may become outdated between invocations, so must be updated before
making filesystem changes.

## Definitions

- workspace: A git workspace, either the original repo or a worktree dir
- octopus: A branch that is on top of an n-way merge

## Changing Directory

It is not possible to `cd` from python. For commands that "change directory":
- By default, output instructions for changing directory or setting up an alias
- Accept a `--destination` flag, output only the directory to stdout, to be
  used by user aliases or bash functions

## Merge strategy

Only allow clean merge/rebase/cherry-pick. If an operation results in a git
conflict, show an error message with a suggestion on how to get git into a
state that would allow the operation.

## Use Cases

In all cases, when a command is executed:

- Start tracking this git repo in `workspaces.json`
- Commands should work the same regardless if run from original repo dir
  or from worktree dir
- All short flags should also have long flags (e.g. `-b,--branch`)

### Creating a new branch and worktree

```
$ gitcuttle new [BRANCH] [-b NAME]
```

- Creates a new branch and worktree in `$XDG_DATA_HOME/gitcuttle/<repo>/<branch>`
- Use given BRANCH as base. If not provided, use current commit as the base
- If BRANCH is given but does not exist, show an error message, suggest 
  `new -b NAME` (no BRANCH)
- Branch name is provided with `-b NAME` or generated using a random inverse 
  hex (e.g. `workspace-zyxwvut`)
  - If given branch name contains `/`, it should be sanitized in the dir name,
    but kept in the git branch name
- If branch already exists, then show an error message
- Change directory to workspace dir

#### Creating an octopus branch

```
$ gitcuttle new BRANCH [BRANCH...] [-b NAME]
```

- Create a new workspace and branch that is an n-way (octopus) merge with
  given branches
- Track all bases in `workspaces.json`

### List workspaces

```
$ gitcuttle list
```

Table of tracked workspaces (leave blank if n/a)
- repo name
- branch name
- dirty status
- remote status: ahead/behind
- PR status: draft/open/merged
- description (PR title or last commit)

### Delete workspace

```
$ gitcuttle delete BRANCH [--dry-run]
```

- Delete the tracked BRANCH workspace (worktree and branch)
- If BRANCH is not a tracked workspace show an error message with a suggestion
  to delete using git cli

### Prune

```
$ gitcuttle prune [--dry-run]
```

- Delete all workspaces whose remote branches have been merged or deleted

### Updating a branch

```
$ gitcuttle update
```

- Rebase current branch onto the remote branch
- Handle octopus branches:
  - Individually rebase each parent branch
  - Do a new n-way merge
  - Cherry-pick original post-merge branches

### Absorbing a change (octopus branch)

```
$ gitcuttle absorb [BRANCH] [-i]
```

- If not on octopus workspace, show an error
- If BRANCH is given, rebase post-merge commits onto branch and rebase the
  octopus merge
- If `-i` is given, have user interactively select a branch for each
  post-merge commit
- If no args given, heuristically determine which branch each commit should go
  based on the branches' edited files. If not possible to do reliably, show
  an error and suggest doing interactively.

