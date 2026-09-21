"""Aether Workspace system — workspaces and layouts.

Architecture:
    Workspace = what panels exist, startup behavior
    Layout    = where panels are positioned

    WorkspaceManager owns both concepts and provides lifecycle management.
"""

from aether.workspace.i_workspace import IWorkspace
from aether.workspace.i_layout import ILayout
from aether.workspace.i_interaction_target import IInteractionTarget
from aether.workspace.workspace_manager import WorkspaceManager

__all__ = [
    "IWorkspace",
    "ILayout",
    "IInteractionTarget",
    "WorkspaceManager",
]
