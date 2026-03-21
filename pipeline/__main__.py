"""Allow running pipeline as: python -m pipeline"""

from pipeline.cli import main
import sys

sys.exit(main())
