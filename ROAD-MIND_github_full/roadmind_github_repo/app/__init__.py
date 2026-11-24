"""Roadmind — AI traffic-signal advisor."""
import warnings

# supervision prints harmless deprecation notices on import; keep the terminal readable
warnings.filterwarnings("ignore", category=FutureWarning, module=r"supervision(\..*)?")
