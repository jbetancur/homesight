package weather

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/nathan-osman/go-sunrise"
)

// Service manages weather data fetching and caching
type Service struct {
	zipCode      string
	locationName string
	lat          float64
	lon          float64
	userAgent    string

	cache         *EnvironmentalContext
	cacheMu       sync.RWMutex
	cacheDuration time.Duration

	ctx    context.Context
	cancel context.CancelFunc
}

// EnvironmentalContext represents complete environmental data
type EnvironmentalContext struct {
	Weather  WeatherData `json:"weather"`
	Sun      SunTimes    `json:"sun"`
	Location string      `json:"location"`
	CachedAt time.Time   `json:"cached_at"`
}

// WeatherData represents current weather conditions
type WeatherData struct {
	Temperature  float64   `json:"temperature"`
	Humidity     int       `json:"humidity"`
	Pressure     int       `json:"pressure"`
	Description  string    `json:"description"`
	Icon         string    `json:"icon"`
	WindSpeed    float64   `json:"wind_speed"`
	WindDir      *float64  `json:"wind_direction,omitempty"`
	Clouds       int       `json:"clouds"`
	Visibility   int       `json:"visibility"`
	UVIndex      *float64  `json:"uv_index,omitempty"`
	Precipitation *float64 `json:"precipitation,omitempty"`
	Timestamp    time.Time `json:"timestamp"`
}

// SunTimes represents sunrise and sunset times
type SunTimes struct {
	Sunrise       time.Time `json:"sunrise"`
	Sunset        time.Time `json:"sunset"`
	DayLengthHours float64  `json:"day_length_hours"`
}

// Met.no weather symbol mapping
var weatherSymbols = map[string]struct {
	Description string
	Icon        string
}{
	"clearsky":                {"Clear sky", "01d"},
	"fair":                    {"Fair", "02d"},
	"partlycloudy":            {"Partly cloudy", "03d"},
	"cloudy":                  {"Cloudy", "04d"},
	"rainshowers":             {"Rain showers", "09d"},
	"rainshowersandthunder":   {"Thunderstorms", "11d"},
	"sleetshowers":            {"Sleet showers", "13d"},
	"snowshowers":             {"Snow showers", "13d"},
	"rain":                    {"Rain", "10d"},
	"heavyrain":               {"Heavy rain", "10d"},
	"heavyrainandthunder":     {"Heavy thunderstorms", "11d"},
	"sleet":                   {"Sleet", "13d"},
	"snow":                    {"Snow", "13d"},
	"snowandthunder":          {"Snow and thunder", "13d"},
	"fog":                     {"Fog", "50d"},
	"sleetshowersandthunder":  {"Sleet and thunder", "11d"},
	"snowshowersandthunder":   {"Snow and thunder", "11d"},
	"rainandthunder":          {"Rain and thunder", "11d"},
	"sleetandthunder":         {"Sleet and thunder", "11d"},
	"lightrainshowers":        {"Light rain showers", "09d"},
	"heavyrainshowers":        {"Heavy rain showers", "09d"},
	"lightsleetshowers":       {"Light sleet showers", "13d"},
	"heavysleetshowers":       {"Heavy sleet showers", "13d"},
	"lightsnowshowers":        {"Light snow showers", "13d"},
	"heavysnowshowers":        {"Heavy snow showers", "13d"},
	"lightrain":               {"Light rain", "10d"},
	"lightsleet":              {"Light sleet", "13d"},
	"heavysleet":              {"Heavy sleet", "13d"},
	"lightsnow":               {"Light snow", "13d"},
	"heavysnow":               {"Heavy snow", "13d"},
}

// NewService creates a new weather service
func NewService(ctx context.Context, zipCode string) (*Service, error) {
	svcCtx, cancel := context.WithCancel(ctx)

	s := &Service{
		zipCode:       zipCode,
		userAgent:     "HomeSight/1.0 (https://github.com/jbetancur/homesight)",
		cacheDuration: 15 * time.Minute,
		ctx:           svcCtx,
		cancel:        cancel,
	}

	// Geocode ZIP immediately
	if err := s.geocodeZIP(); err != nil {
		cancel()
		return nil, fmt.Errorf("failed to geocode ZIP %s: %w", zipCode, err)
	}

	// Start background refresh
	go s.refreshLoop()

	return s, nil
}

// Stop shuts down the weather service
func (s *Service) Stop() {
	s.cancel()
}

// GetCurrent returns cached weather data
func (s *Service) GetCurrent() *EnvironmentalContext {
	s.cacheMu.RLock()
	defer s.cacheMu.RUnlock()
	return s.cache
}

// Refresh forces a weather data refresh
func (s *Service) Refresh() error {
	return s.fetchWeather()
}

// refreshLoop periodically refreshes weather data
func (s *Service) refreshLoop() {
	// Fetch immediately
	if err := s.fetchWeather(); err != nil {
		log.Printf("[WEATHER] Initial fetch failed: %v", err)
	}

	ticker := time.NewTicker(15 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-s.ctx.Done():
			return
		case <-ticker.C:
			if err := s.fetchWeather(); err != nil {
				log.Printf("[WEATHER] Refresh failed: %v", err)
			}
		}
	}
}

// geocodeZIP converts ZIP code to lat/lon using Zippopotam.us API
func (s *Service) geocodeZIP() error {
	url := fmt.Sprintf("https://api.zippopotam.us/us/%s", s.zipCode)

	resp, err := http.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("geocoding failed with status %d", resp.StatusCode)
	}

	var result struct {
		Places []struct {
			PlaceName string `json:"place name"`
			State     string `json:"state abbreviation"`
			Latitude  string `json:"latitude"`
			Longitude string `json:"longitude"`
		} `json:"places"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return err
	}

	if len(result.Places) == 0 {
		return fmt.Errorf("no results for ZIP %s", s.zipCode)
	}

	place := result.Places[0]
	fmt.Sscanf(place.Latitude, "%f", &s.lat)
	fmt.Sscanf(place.Longitude, "%f", &s.lon)
	s.locationName = fmt.Sprintf("%s, %s", place.PlaceName, place.State)

	log.Printf("[WEATHER] Geocoded ZIP %s to %s (%.4f, %.4f)", s.zipCode, s.locationName, s.lat, s.lon)
	return nil
}

// fetchWeather retrieves weather from Met.no API
func (s *Service) fetchWeather() error {
	client := &http.Client{Timeout: 10 * time.Second}

	// Fetch from Met.no
	url := fmt.Sprintf("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%.4f&lon=%.4f", s.lat, s.lon)

	req, err := http.NewRequestWithContext(s.ctx, "GET", url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", s.userAgent)

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Met.no returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	var metData struct {
		Properties struct {
			Timeseries []struct {
				Time string `json:"time"`
				Data struct {
					Instant struct {
						Details struct {
							AirTemp          float64  `json:"air_temperature"`
							RelativeHumidity float64  `json:"relative_humidity"`
							AirPressure      float64  `json:"air_pressure_at_sea_level"`
							WindSpeed        float64  `json:"wind_speed"`
							WindFromDir      *float64 `json:"wind_from_direction"`
							CloudAreaFrac    float64  `json:"cloud_area_fraction"`
							UVIndex          *float64 `json:"ultraviolet_index_clear_sky"`
						} `json:"details"`
					} `json:"instant"`
					Next1Hours *struct {
						Summary struct {
							SymbolCode string `json:"symbol_code"`
						} `json:"summary"`
						Details struct {
							PrecipAmount *float64 `json:"precipitation_amount"`
						} `json:"details"`
					} `json:"next_1_hours"`
					Next6Hours *struct {
						Summary struct {
							SymbolCode string `json:"symbol_code"`
						} `json:"summary"`
					} `json:"next_6_hours"`
				} `json:"data"`
			} `json:"timeseries"`
		} `json:"properties"`
	}

	if err := json.Unmarshal(body, &metData); err != nil {
		return err
	}

	if len(metData.Properties.Timeseries) == 0 {
		return fmt.Errorf("no timeseries data from Met.no")
	}

	current := metData.Properties.Timeseries[0]
	instant := current.Data.Instant.Details

	// Get symbol code
	symbolCode := ""
	if current.Data.Next1Hours != nil {
		symbolCode = current.Data.Next1Hours.Summary.SymbolCode
	} else if current.Data.Next6Hours != nil {
		symbolCode = current.Data.Next6Hours.Summary.SymbolCode
	}

	// Strip day/night suffix
	symbolCode = stripSuffix(symbolCode, "_day")
	symbolCode = stripSuffix(symbolCode, "_night")
	symbolCode = stripSuffix(symbolCode, "_polartwilight")

	desc, icon := "Unknown", "01d"
	if sym, ok := weatherSymbols[symbolCode]; ok {
		desc = sym.Description
		icon = sym.Icon
	}

	// Convert units
	tempF := instant.AirTemp*9/5 + 32
	windMPH := instant.WindSpeed * 2.237
	humidity := int(instant.RelativeHumidity)

	// Precipitation (convert mm to inches)
	var precip *float64
	if current.Data.Next1Hours != nil && current.Data.Next1Hours.Details.PrecipAmount != nil {
		p := *current.Data.Next1Hours.Details.PrecipAmount / 25.4
		precip = &p
	}

	weather := WeatherData{
		Temperature:   tempF,
		Humidity:      humidity,
		Pressure:      int(instant.AirPressure),
		Description:   desc,
		Icon:          icon,
		WindSpeed:     windMPH,
		WindDir:       instant.WindFromDir,
		Clouds:        int(instant.CloudAreaFrac),
		Visibility:    10000, // Met.no doesn't provide visibility
		UVIndex:       instant.UVIndex,
		Precipitation: precip,
		Timestamp:     time.Now(),
	}

	// Calculate sun times with proper timezone
	sunTimes := s.calculateSunTimes()

	// Build context
	ctx := &EnvironmentalContext{
		Weather:  weather,
		Sun:      sunTimes,
		Location: s.locationName,
		CachedAt: time.Now(),
	}

	s.cacheMu.Lock()
	s.cache = ctx
	s.cacheMu.Unlock()

	log.Printf("[WEATHER] Updated: %s - %.1f°F, %s (sunrise: %s, sunset: %s)",
		s.locationName, tempF, desc,
		sunTimes.Sunrise.Format("3:04 PM MST"),
		sunTimes.Sunset.Format("3:04 PM MST"))

	return nil
}

// calculateSunTimes computes sunrise/sunset in UTC
func (s *Service) calculateSunTimes() SunTimes {
	now := time.Now().UTC()
	year, month, day := now.Date()

	// Calculate sunrise/sunset - library returns UTC times
	sunrise, sunset := sunrise.SunriseSunset(s.lat, s.lon, year, month, day)

	// Force to UTC timezone (library may return with wrong zone info)
	sunrise = time.Date(sunrise.Year(), sunrise.Month(), sunrise.Day(),
		sunrise.Hour(), sunrise.Minute(), sunrise.Second(), 0, time.UTC)
	sunset = time.Date(sunset.Year(), sunset.Month(), sunset.Day(),
		sunset.Hour(), sunset.Minute(), sunset.Second(), 0, time.UTC)

	dayLength := sunset.Sub(sunrise).Hours()

	return SunTimes{
		Sunrise:        sunrise,
		Sunset:         sunset,
		DayLengthHours: dayLength,
	}
}

// Helper functions

func stripSuffix(s, suffix string) string {
	if len(s) >= len(suffix) && s[len(s)-len(suffix):] == suffix {
		return s[:len(s)-len(suffix)]
	}
	return s
}
