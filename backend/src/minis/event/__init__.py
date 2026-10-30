"""Find a UQ room, preview its tour and prepare booking forms and risk documents

Expose the validated document pipeline and editable source writer through
a small lazy public interface. Importing the mini does not load Word
rendering, read credentials or submit an application
"""

lazy from uq_minis.minis.event.pipeline import generate
lazy from uq_minis.minis.event.source import save

__all__ = ["generate", "save"]
