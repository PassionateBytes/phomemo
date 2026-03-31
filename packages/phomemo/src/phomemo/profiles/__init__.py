"""Built-In Profiles

Collection of built-in profiles, easily extendable for more devices.
"""

from phomemo.registry import register_profile

from .m08f import M08F_A4, M08F_LETTER

register_profile(M08F_A4)
register_profile(M08F_LETTER)
