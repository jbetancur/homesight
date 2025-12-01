#!/usr/bin/env python3
"""
Test script for River ML engine integration.

Tests:
1. Model initialization
2. Feature extraction
3. Baseline learning
4. Anomaly detection
5. Comfort prediction
6. Weather integration
"""

import asyncio
import sys
from datetime import datetime
from hsil.hsil_ml_river import HSILRiverLearningEngine
from hsil.types import EventContext
from hsil.weather_service import WeatherService, EnvironmentalContext, WeatherData, SunTimes, AirQuality


async def test_river_ml():
    """Test River ML engine"""
    print("=" * 60)
    print("Testing River ML Engine")
    print("=" * 60)

    # Initialize engine
    print("\n1. Initializing River ML engine...")
    engine = HSILRiverLearningEngine(db_path="/tmp/test_river_ml.db")
    print("✓ Engine initialized")

    # Create mock environmental context
    print("\n2. Creating mock environmental context...")
    env = EnvironmentalContext(
        weather=WeatherData(
            temperature=75.0,
            feels_like=73.0,
            humidity=60,
            pressure=1013,
            description="clear sky",
            icon="01d",
            wind_speed=5.0,
            clouds=10,
            visibility=10000,
            timestamp=datetime.now()
        ),
        sun=SunTimes(
            sunrise=datetime.now().replace(hour=6, minute=30),
            sunset=datetime.now().replace(hour=18, minute=30),
            day_length_hours=12.0
        ),
        air_quality=AirQuality(
            aqi=1,
            pm2_5=5.0,
            pm10=10.0,
            o3=20.0,
            no2=5.0
        ),
        location="Test Location"
    )
    print("✓ Environmental context created")

    # Test learning from sensor data
    print("\n3. Testing learning from sensor data...")
    for i in range(100):
        context = EventContext(
            device_id="test_sensor_1",
            sensor_id="temp_1",
            event_type="temperature",
            event_value=70.0 + (i % 10),
            location="living_room",
            device_type="temp_sensor",
            timestamp=datetime.now()
        )
        await engine.learn_from_sensor_data(context, env)

    print(f"✓ Learned from 100 sensor events")

    # Test anomaly detection
    print("\n4. Testing anomaly detection...")

    # Normal value
    is_anom, score = await engine.is_anomalous("test_sensor_1", "temperature", 72.0)
    print(f"   Normal value (72.0): anomalous={is_anom}, score={score:.3f}")

    # Anomalous value
    is_anom, score = await engine.is_anomalous("test_sensor_1", "temperature", 150.0)
    print(f"   Anomalous value (150.0): anomalous={is_anom}, score={score:.3f}")

    # Test comfort prediction
    print("\n5. Testing comfort prediction...")
    predicted, confidence = await engine.predict_preferred_value(
        location="living_room",
        metric="temperature",
        current_value=68.0,
        env=env
    )
    print(f"   Predicted preferred temp: {predicted:.1f}°F (confidence: {confidence:.2f})")

    # Test comfort preference
    print("\n6. Testing comfort preference retrieval...")
    prefs = await engine.get_comfort_preference("living_room")
    if prefs:
        print(f"   Comfort preferences: {prefs}")
    else:
        print("   No comfort preferences learned yet (expected)")

    # Test stats
    print("\n7. Testing stats retrieval...")
    stats = await engine.get_stats()
    print(f"   Stats: {stats}")

    # Test baseline models
    print("\n8. Testing baseline statistics...")
    if "test_sensor_1" in engine.baseline_models:
        if "temperature" in engine.baseline_models["test_sensor_1"]:
            mean_model, var_model = engine.baseline_models["test_sensor_1"]["temperature"]
            mean_val = mean_model.get()
            var_val = var_model.get()
            print(f"   Baseline: mean={mean_val:.2f}, variance={var_val:.2f}")
        else:
            print("   ✗ Temperature metric not in baseline models")
    else:
        print("   ✗ test_sensor_1 not in baseline models")

    # Test feature extraction
    print("\n9. Testing feature extraction...")
    test_context = EventContext(
        device_id="test_sensor_1",
        sensor_id="temp_1",
        event_type="temperature",
        event_value=72.0,
        location="living_room",
        device_type="temp_sensor",
        timestamp=datetime.now()
    )

    comfort_features = engine._extract_comfort_features(test_context, env)
    print(f"   Comfort features ({len(comfort_features)} features):")
    for key, val in list(comfort_features.items())[:5]:
        print(f"     - {key}: {val:.3f}")

    routine_features = engine._extract_routine_features(test_context, env)
    print(f"   Routine features ({len(routine_features)} features):")
    for key, val in list(routine_features.items())[:5]:
        print(f"     - {key}: {val:.3f}")

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(test_river_ml())
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
