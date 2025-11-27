package discovery

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ZWaveUSBReceiver represents a detected Z-Wave USB stick
type ZWaveUSBReceiver struct {
	Name         string
	DevicePath   string
	VendorID     string
	ProductID    string
	SerialNumber string
	Online       bool
}

// DiscoverZWaveUSBReceivers finds Z-Wave USB sticks connected to the system
func DiscoverZWaveUSBReceivers() ([]ZWaveUSBReceiver, error) {
	receivers := []ZWaveUSBReceiver{}

	// Check /dev/serial/by-id/ for Z-Wave devices
	serialByIDPath := "/dev/serial/by-id"
	entries, err := os.ReadDir(serialByIDPath)
	if err != nil {
		// If /dev/serial/by-id doesn't exist, try checking ttyACM* and ttyUSB* directly
		return checkTTYDevices()
	}

	for _, entry := range entries {
		name := entry.Name()

		// Look for common Z-Wave USB stick identifiers
		if isZWaveDevice(name) {
			devicePath := filepath.Join(serialByIDPath, name)

			// Resolve the symlink to get the actual device path
			realPath, err := filepath.EvalSymlinks(devicePath)
			if err != nil {
				continue
			}

			// Check if device is accessible (online)
			online := isDeviceAccessible(realPath)

			receiver := ZWaveUSBReceiver{
				Name:       formatDeviceName(name),
				DevicePath: realPath,
				Online:     online,
			}

			// Extract vendor/product info from the device name
			extractDeviceInfo(&receiver, name)

			receivers = append(receivers, receiver)
		}
	}

	return receivers, nil
}

// isZWaveDevice checks if the device name indicates a Z-Wave USB stick
func isZWaveDevice(name string) bool {
	nameLower := strings.ToLower(name)

	// Common Z-Wave USB stick identifiers
	zWaveIdentifiers := []string{
		"z-wave",
		"zwave",
		"zooz",
		"aeotec",
		"sigma_designs",
		"0658:0200", // Aeotec Z-Stick
		"10c4:8a2a", // Aeotec Z-Stick Gen5
		"0658:0280", // Aeotec Z-Stick 7
		"1a86:55d4", // Zooz 800 Z-Wave Stick
	}

	for _, identifier := range zWaveIdentifiers {
		if strings.Contains(nameLower, identifier) {
			return true
		}
	}

	return false
}

// checkTTYDevices checks ttyACM* and ttyUSB* devices for Z-Wave sticks
func checkTTYDevices() ([]ZWaveUSBReceiver, error) {
	receivers := []ZWaveUSBReceiver{}
	devPath := "/dev"

	entries, err := os.ReadDir(devPath)
	if err != nil {
		return receivers, fmt.Errorf("failed to read /dev: %w", err)
	}

	for _, entry := range entries {
		name := entry.Name()

		// Check ttyACM and ttyUSB devices
		if strings.HasPrefix(name, "ttyACM") || strings.HasPrefix(name, "ttyUSB") {
			devicePath := filepath.Join(devPath, name)

			// Check if accessible
			if isDeviceAccessible(devicePath) {
				// Try to identify it as a Z-Wave device through sysfs
				if isZWaveDeviceFromSysfs(name) {
					receiver := ZWaveUSBReceiver{
						Name:       fmt.Sprintf("Z-Wave USB Receiver (%s)", name),
						DevicePath: devicePath,
						Online:     true,
					}
					receivers = append(receivers, receiver)
				}
			}
		}
	}

	return receivers, nil
}

// isZWaveDeviceFromSysfs checks sysfs to identify Z-Wave USB devices
func isZWaveDeviceFromSysfs(ttyName string) bool {
	// Check /sys/class/tty/ttyACMX/device for USB vendor/product info
	sysfsPath := filepath.Join("/sys/class/tty", ttyName, "device")

	// Read vendor ID
	vendorPath := filepath.Join(sysfsPath, "../idVendor")
	vendorBytes, err := os.ReadFile(vendorPath)
	if err != nil {
		return false
	}
	vendor := strings.TrimSpace(string(vendorBytes))

	// Read product ID
	productPath := filepath.Join(sysfsPath, "../idProduct")
	productBytes, err := os.ReadFile(productPath)
	if err != nil {
		return false
	}
	product := strings.TrimSpace(string(productBytes))

	// Check against known Z-Wave USB stick vendor/product IDs
	knownZWaveIDs := map[string][]string{
		"0658": {"0200", "0280"}, // Aeotec
		"10c4": {"8a2a"},          // Silicon Labs (Aeotec Gen5)
		"1a86": {"55d4"},          // Zooz 800
	}

	if productIDs, ok := knownZWaveIDs[vendor]; ok {
		for _, pid := range productIDs {
			if pid == product {
				return true
			}
		}
	}

	return false
}

// isDeviceAccessible checks if the device file is accessible
func isDeviceAccessible(devicePath string) bool {
	_, err := os.Stat(devicePath)
	return err == nil
}

// formatDeviceName formats the device name for display
func formatDeviceName(name string) string {
	// Remove common prefixes
	name = strings.TrimPrefix(name, "usb-")

	// Replace underscores and hyphens with spaces
	name = strings.ReplaceAll(name, "_", " ")
	name = strings.ReplaceAll(name, "-if00", "")

	return name
}

// extractDeviceInfo extracts vendor, product, and serial info from device name
func extractDeviceInfo(receiver *ZWaveUSBReceiver, name string) {
	// Example: usb-Zooz_800_Z-Wave_Stick_533D004242-if00
	parts := strings.Split(name, "_")

	// Try to find serial number (usually alphanumeric string at the end)
	for _, part := range parts {
		if len(part) > 8 && isAlphaNumeric(part) {
			receiver.SerialNumber = part
			break
		}
	}
}

// isAlphaNumeric checks if a string contains only alphanumeric characters
func isAlphaNumeric(s string) bool {
	for _, r := range s {
		if !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
			return false
		}
	}
	return true
}
