import pytest

from cycling_coach.profile import AthleteProfile


@pytest.fixture
def athlete() -> AthleteProfile:
    """A 72 kg rider with a 70 g/h demonstrated carb tolerance."""
    return AthleteProfile(
        name="Test", birth_date=None, sex="male", height_cm=178, weight_kg=72.0,
        ftp_w=250, ftp_source="ramp_test", ftp_updated=None, max_hr=190, lthr=168,
        resting_hr=48, vo2max=None, w_prime_j=None,
        sweat_measured=True, sweat_rate_l_per_h=0.9, sweat_sodium_mg_per_l=800,
        sweat_reference_temp_c=18,
        gut_trained_carb_g_per_h=70, caffeine_mg_per_kg=3.0, restrictions=[],
        preferred_products=[],
        weekly_hours=8, days_available=[], long_ride_day="sat", discipline="road",
        max_ramp_rate=5, goals=[],
    )
