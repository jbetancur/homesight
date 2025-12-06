package timezone

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Service handles timezone detection and conversion
type Service struct {
	timezone *time.Location
	zipCode  string
}

// NewService creates a new timezone service
func NewService(configTimezone, zipCode string) (*Service, error) {
	s := &Service{
		zipCode: zipCode,
	}

	var tz string
	if configTimezone == "" || configTimezone == "auto" {
		// Auto-detect from ZIP code
		detected, err := s.detectFromZipCode(zipCode)
		if err != nil {
			// Fallback to UTC if detection fails
			tz = "UTC"
		} else {
			tz = detected
		}
	} else {
		tz = configTimezone
	}

	loc, err := time.LoadLocation(tz)
	if err != nil {
		return nil, fmt.Errorf("invalid timezone %s: %w", tz, err)
	}

	s.timezone = loc
	return s, nil
}

// GetLocation returns the current time.Location
func (s *Service) GetLocation() *time.Location {
	return s.timezone
}

// GetName returns the IANA timezone name
func (s *Service) GetName() string {
	return s.timezone.String()
}

// Now returns the current time in the configured timezone
func (s *Service) Now() time.Time {
	return time.Now().In(s.timezone)
}

// Convert converts a UTC time to the configured timezone
func (s *Service) Convert(utcTime time.Time) time.Time {
	return utcTime.In(s.timezone)
}

// FormatLocal formats a UTC time in the local timezone
func (s *Service) FormatLocal(utcTime time.Time, layout string) string {
	return s.Convert(utcTime).Format(layout)
}

// detectFromZipCode detects timezone from US ZIP code using zippopotam.us API
func (s *Service) detectFromZipCode(zipCode string) (string, error) {
	if zipCode == "" {
		return "", fmt.Errorf("no ZIP code provided")
	}

	url := fmt.Sprintf("https://api.zippopotam.us/us/%s", zipCode)
	resp, err := http.Get(url)
	if err != nil {
		return "", fmt.Errorf("failed to fetch ZIP data: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("invalid ZIP code: %s", zipCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read response: %w", err)
	}

	var result struct {
		Places []struct {
			State     string `json:"state"`
			StateAbbr string `json:"state abbreviation"`
			PlaceName string `json:"place name"`
			Longitude string `json:"longitude"`
			Latitude  string `json:"latitude"`
		} `json:"places"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return "", fmt.Errorf("failed to parse response: %w", err)
	}

	if len(result.Places) == 0 {
		return "", fmt.Errorf("no location found for ZIP: %s", zipCode)
	}

	// Map US state abbreviations to IANA timezones
	stateAbbr := result.Places[0].StateAbbr
	tz := stateToTimezone(stateAbbr)

	if tz == "" {
		return "", fmt.Errorf("could not determine timezone for state: %s", stateAbbr)
	}

	return tz, nil
}

// stateToTimezone maps US state abbreviations to IANA timezones
func stateToTimezone(state string) string {
	timezones := map[string]string{
		// Eastern Time
		"CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
		"GA": "America/New_York", "ME": "America/New_York", "MD": "America/New_York",
		"MA": "America/New_York", "NH": "America/New_York", "NJ": "America/New_York",
		"NY": "America/New_York", "NC": "America/New_York", "OH": "America/New_York",
		"PA": "America/New_York", "RI": "America/New_York", "SC": "America/New_York",
		"VT": "America/New_York", "VA": "America/New_York", "WV": "America/New_York",
		"DC": "America/New_York",

		// Central Time
		"AL": "America/Chicago", "AR": "America/Chicago", "IL": "America/Chicago",
		"IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/Chicago",
		"LA": "America/Chicago", "MN": "America/Chicago", "MS": "America/Chicago",
		"MO": "America/Chicago", "NE": "America/Chicago", "ND": "America/Chicago",
		"OK": "America/Chicago", "SD": "America/Chicago", "TN": "America/Chicago",
		"TX": "America/Chicago", "WI": "America/Chicago",

		// Mountain Time
		"AZ": "America/Phoenix", "CO": "America/Denver", "ID": "America/Denver",
		"MT": "America/Denver", "NM": "America/Denver", "UT": "America/Denver",
		"WY": "America/Denver",

		// Pacific Time
		"CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
		"OR": "America/Los_Angeles", "WA": "America/Los_Angeles",

		// Alaska & Hawaii
		"AK": "America/Anchorage",
		"HI": "Pacific/Honolulu",
	}

	return timezones[strings.ToUpper(state)]
}

// ValidateTimezone checks if a timezone string is valid
func ValidateTimezone(tz string) error {
	if tz == "" || tz == "auto" {
		return nil
	}
	_, err := time.LoadLocation(tz)
	return err
}

// ListCommonTimezones returns a list of common US timezones
func ListCommonTimezones() []string {
	return []string{
		"America/New_York",
		"America/Chicago",
		"America/Denver",
		"America/Phoenix",
		"America/Los_Angeles",
		"America/Anchorage",
		"Pacific/Honolulu",
		"UTC",
	}
}
