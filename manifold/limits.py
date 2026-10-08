"""Shared, finite transfer/model bounds; these are not engineering approvals.

The editable project permits 120 total features (including generated drillings)
and 40 nets. Recognition may retain a larger circuit for review; generation must
fit the project model rather than silently dropping its topology.
"""
PROJECT_FEATURES = 120
PROJECT_NETS = 40
COMPONENT_INTERFACES = 64
ANALYSIS_COMPONENTS = PROJECT_FEATURES
ANALYSIS_PORTS = 600
ANALYSIS_NETS = 300
NET_MEMBERS = 100
