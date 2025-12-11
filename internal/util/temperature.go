package util

// TemperatureUnit represents the unit of temperature measurement
type TemperatureUnit string

const (
	Celsius    TemperatureUnit = "celsius"
	Fahrenheit TemperatureUnit = "fahrenheit"
)

// CelsiusToFahrenheit converts Celsius to Fahrenheit
func CelsiusToFahrenheit(c float64) float64 {
	return (c * 9.0 / 5.0) + 32.0
}

// FahrenheitToCelsius converts Fahrenheit to Celsius
func FahrenheitToCelsius(f float64) float64 {
	return (f - 32.0) * 5.0 / 9.0
}

// ConvertTemperature converts between temperature units
func ConvertTemperature(value float64, from, to TemperatureUnit) float64 {
	if from == to {
		return value
	}

	if from == Celsius && to == Fahrenheit {
		return CelsiusToFahrenheit(value)
	}

	if from == Fahrenheit && to == Celsius {
		return FahrenheitToCelsius(value)
	}

	return value
}

// NormalizeToPreferredUnit converts temperature to user's preferred unit
// ZWave sensors report "Air temperature" in Celsius
func NormalizeToPreferredUnit(value float64, sensorUnit TemperatureUnit, preferredUnit string) float64 {
	preferred := TemperatureUnit(preferredUnit)
	return ConvertTemperature(value, sensorUnit, preferred)
}
