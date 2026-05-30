# ============================================================
# tests/test_config.py — Config Validation Tests
# ============================================================
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfigValidation:
    def test_valid_config_passes(self):
        from infra.config import validate_config
        # Should not raise
        validate_config()

    def test_invalid_capital_raises(self):
        import infra.config as cfg
        original = cfg.CAPITAL
        try:
            cfg.CAPITAL = -1000
            with pytest.raises(ValueError, match="CAPITAL"):
                cfg.validate_config()
        finally:
            cfg.CAPITAL = original

    def test_invalid_risk_raises(self):
        import infra.config as cfg
        original = cfg.RISK_PER_TRADE
        try:
            cfg.RISK_PER_TRADE = 0.5   # 50% risk — way too high
            with pytest.raises(ValueError, match="RISK_PER_TRADE"):
                cfg.validate_config()
        finally:
            cfg.RISK_PER_TRADE = original

    def test_invalid_daily_loss_raises(self):
        import infra.config as cfg
        original = cfg.DAILY_LOSS_LIMIT
        try:
            cfg.DAILY_LOSS_LIMIT = 0.5   # 50% daily loss — insane
            with pytest.raises(ValueError, match="DAILY_LOSS_LIMIT"):
                cfg.validate_config()
        finally:
            cfg.DAILY_LOSS_LIMIT = original


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
