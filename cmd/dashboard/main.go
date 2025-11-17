package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	hsmodel "github.com/homesight/homesight/internal/model"
)

const (
	apiURL = "http://localhost:8080"
)

// Styles
var (
	// Main title with gradient effect
	titleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#00D9FF")).
			Background(lipgloss.Color("#0A1628")).
			BorderStyle(lipgloss.DoubleBorder()).
			BorderForeground(lipgloss.Color("#00D9FF")).
			Padding(0, 2).
			MarginBottom(1).
			Width(60).
			Align(lipgloss.Center)

	subtitleStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#888888")).
			Italic(true).
			Align(lipgloss.Center)

	headerStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#FFFFFF")).
			Background(lipgloss.Color("#1E3A5F")).
			Padding(0, 1).
			MarginBottom(1)

	statusOKStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#00FF88")).
			Bold(true)

	statusWarnStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#FFB800")).
			Bold(true)

	statusErrorStyle = lipgloss.NewStyle().
				Foreground(lipgloss.Color("#FF3366")).
				Bold(true)

	boxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#00D9FF")).
			Padding(1, 2).
			MarginTop(1).
			MarginBottom(1)

	deviceBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#9D4EDD")).
			Padding(1, 2).
			MarginTop(1)

	incidentBoxStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(lipgloss.Color("#FF006E")).
				Padding(1, 2).
				MarginTop(1)

	helpStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#666666")).
			Background(lipgloss.Color("#0A1628")).
			Padding(1, 2).
			MarginTop(1).
			Width(60).
			Align(lipgloss.Center)

	labelStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#00D9FF")).
			Bold(true)

	valueStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#FFFFFF"))

	mutedStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#666666")).
			Italic(true)
)

type tickMsg time.Time
type dataMsg struct {
	health    map[string]interface{}
	devices   []hsmodel.Device
	incidents []hsmodel.Incident
	err       error
}

type dashModel struct {
	health     map[string]interface{}
	devices    []hsmodel.Device
	incidents  []hsmodel.Incident
	err        error
	quitting   bool
	width      int
	height     int
	lastUpdate time.Time
	spinner    int
}

func initialModel() dashModel {
	return dashModel{}
}

func (m dashModel) Init() tea.Cmd {
	return tea.Batch(
		tickCmd(),
		fetchData(),
	)
}

func (m dashModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q":
			m.quitting = true
			return m, tea.Quit
		case "r":
			return m, fetchData()
		}

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case tickMsg:
		m.spinner = (m.spinner + 1) % 4
		return m, tea.Batch(
			tickCmd(),
			fetchData(),
		)

	case dataMsg:
		m.health = msg.health
		m.devices = msg.devices
		m.incidents = msg.incidents
		m.err = msg.err
		m.lastUpdate = time.Now()
	}

	return m, nil
}

func (m dashModel) View() string {
	if m.quitting {
		return lipgloss.NewStyle().
			Foreground(lipgloss.Color("#00FF88")).
			Bold(true).
			Padding(2).
			Render("👋 Goodbye! Thanks for using HomeSight\n")
	}

	// Spinner animation
	spinners := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
	spinner := spinners[m.spinner%len(spinners)]

	var sections []string

	// Title with emoji and subtitle
	title := titleStyle.Render("🏠  H O M E S I G H T  D A S H B O A R D")
	subtitle := subtitleStyle.Render("Real-time Home Monitoring System")
	sections = append(sections, title, subtitle)

	// Status section with enhanced styling
	statusSection := m.renderStatus(spinner)
	sections = append(sections, boxStyle.Render(statusSection))

	// Two-column layout for devices and incidents
	leftColumn := m.renderDevices()
	rightColumn := m.renderIncidents()

	columns := lipgloss.JoinHorizontal(
		lipgloss.Top,
		deviceBoxStyle.Width(50).Render(leftColumn),
		"  ",
		incidentBoxStyle.Width(50).Render(rightColumn),
	)
	sections = append(sections, columns)

	// Enhanced help text with more info
	updateInfo := ""
	if !m.lastUpdate.IsZero() {
		elapsed := time.Since(m.lastUpdate)
		updateInfo = fmt.Sprintf(" • Last update: %ds ago", int(elapsed.Seconds()))
	}

	help := helpStyle.Render(
		"⌨️  Controls: " +
			labelStyle.Render("r") + " refresh  " +
			labelStyle.Render("q") + " quit" +
			mutedStyle.Render(updateInfo),
	)
	sections = append(sections, help)

	return lipgloss.JoinVertical(lipgloss.Left, sections...)
}

func (m dashModel) renderStatus(spinner string) string {
	if m.err != nil {
		return headerStyle.Render("⚠️  SYSTEM STATUS") + "\n\n" +
			statusErrorStyle.Render("❌ Error") + "\n" +
			mutedStyle.Render(m.err.Error())
	}

	status := "⚠️  Unknown"
	statusStyle := statusWarnStyle
	statusIcon := "⚠️ "

	if m.health != nil {
		if healthStatus, ok := m.health["status"].(string); ok && healthStatus == "healthy" {
			status = "Healthy"
			statusStyle = statusOKStyle
			statusIcon = "✅"
		}
	}

	uptime := time.Now().Format("15:04:05")

	// Create a nice status display
	statusLine := lipgloss.JoinHorizontal(
		lipgloss.Left,
		labelStyle.Render("Status: "),
		statusStyle.Render(statusIcon+" "+status),
		"  ",
		labelStyle.Render(spinner+" "),
		mutedStyle.Render("Auto-refresh: 5s"),
	)

	timeLine := lipgloss.JoinHorizontal(
		lipgloss.Left,
		labelStyle.Render("Time: "),
		valueStyle.Render(uptime),
		"  ",
		labelStyle.Render("API: "),
		valueStyle.Render("http://localhost:8080"),
	)

	return headerStyle.Render("📊  SYSTEM STATUS") + "\n\n" +
		statusLine + "\n" +
		timeLine
}

func (m dashModel) renderDevices() string {
	header := headerStyle.Render(fmt.Sprintf("📱  DEVICES (%d)", len(m.devices)))

	if len(m.devices) == 0 {
		return header + "\n\n" +
			mutedStyle.Render("No devices connected yet.\n") +
			mutedStyle.Render("Connect via MQTT, Zigbee2MQTT, or LAN.")
	}

	var deviceList []string
	deviceList = append(deviceList, "") // spacing

	for i, device := range m.devices {
		if i >= 8 { // Show max 8 devices
			remaining := len(m.devices) - 8
			deviceList = append(deviceList, mutedStyle.Render(
				fmt.Sprintf("  ... and %d more devices", remaining)))
			break
		}

		status := "✅"
		statusColor := statusOKStyle
		lastSeen := "just now"

		if !device.LastSeen.IsZero() {
			elapsed := time.Since(device.LastSeen)
			if elapsed > 5*time.Minute {
				status = "⚠️ "
				statusColor = statusWarnStyle
				lastSeen = fmt.Sprintf("%v ago", elapsed.Round(time.Second))
			} else if elapsed < time.Minute {
				lastSeen = fmt.Sprintf("%ds", int(elapsed.Seconds()))
			} else {
				lastSeen = fmt.Sprintf("%dm", int(elapsed.Minutes()))
			}
		}

		deviceType := device.Type
		if deviceType == "" {
			deviceType = "unknown"
		}

		line := lipgloss.JoinHorizontal(
			lipgloss.Left,
			statusColor.Render(status+" "),
			labelStyle.Render(device.Name),
			" ",
			mutedStyle.Render("("+deviceType+")"),
			" • ",
			valueStyle.Render(lastSeen),
		)
		deviceList = append(deviceList, "  "+line)
	}

	return header + "\n" + strings.Join(deviceList, "\n")
}

func (m dashModel) renderIncidents() string {
	header := headerStyle.Render(fmt.Sprintf("🚨  INCIDENTS (%d)", len(m.incidents)))

	if len(m.incidents) == 0 {
		return header + "\n\n" +
			statusOKStyle.Render("  ✅ All clear!") + "\n" +
			mutedStyle.Render("  No active incidents detected.")
	}

	var incidentList []string
	incidentList = append(incidentList, "") // spacing

	for i, incident := range m.incidents {
		if i >= 8 { // Show max 8 incidents
			remaining := len(m.incidents) - 8
			incidentList = append(incidentList, mutedStyle.Render(
				fmt.Sprintf("  ... and %d more incidents", remaining)))
			break
		}

		severity := "🟡"
		severityStyle := statusWarnStyle
		severityText := "MEDIUM"

		switch incident.Severity {
		case "critical":
			severity = "🔴"
			severityStyle = statusErrorStyle
			severityText = "CRITICAL"
		case "high":
			severity = "🟠"
			severityStyle = statusErrorStyle
			severityText = "HIGH"
		case "medium":
			severity = "🟡"
			severityText = "MEDIUM"
		case "low":
			severity = "🟢"
			severityStyle = statusOKStyle
			severityText = "LOW"
		}

		elapsed := time.Since(incident.CreatedAt)
		timeAgo := ""
		if elapsed < time.Minute {
			timeAgo = "just now"
		} else if elapsed < time.Hour {
			timeAgo = fmt.Sprintf("%dm ago", int(elapsed.Minutes()))
		} else {
			timeAgo = fmt.Sprintf("%dh ago", int(elapsed.Hours()))
		}

		titleLine := lipgloss.JoinHorizontal(
			lipgloss.Left,
			severityStyle.Render(severity+" "+severityText),
			" ",
			valueStyle.Render(incident.Title),
		)

		timeLine := mutedStyle.Render("  └─ " + timeAgo)

		incidentList = append(incidentList, "  "+titleLine)
		incidentList = append(incidentList, timeLine)
	}

	return header + "\n" + strings.Join(incidentList, "\n")
}

func tickCmd() tea.Cmd {
	return tea.Tick(5*time.Second, func(t time.Time) tea.Msg {
		return tickMsg(t)
	})
}

func fetchData() tea.Cmd {
	return func() tea.Msg {
		msg := dataMsg{}

		// Fetch health
		resp, err := http.Get(apiURL + "/health")
		if err != nil {
			msg.err = fmt.Errorf("failed to fetch health: %w", err)
			return msg
		}
		defer resp.Body.Close()

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			msg.err = fmt.Errorf("failed to read health response: %w", err)
			return msg
		}

		if err := json.Unmarshal(body, &msg.health); err != nil {
			msg.err = fmt.Errorf("failed to parse health: %w", err)
			return msg
		}

		// Fetch devices
		resp, err = http.Get(apiURL + "/devices")
		if err != nil {
			msg.err = fmt.Errorf("failed to fetch devices: %w", err)
			return msg
		}
		defer resp.Body.Close()

		body, err = io.ReadAll(resp.Body)
		if err != nil {
			msg.err = fmt.Errorf("failed to read devices response: %w", err)
			return msg
		}

		if err := json.Unmarshal(body, &msg.devices); err != nil {
			msg.err = fmt.Errorf("failed to parse devices: %w", err)
			return msg
		}

		// Fetch incidents
		resp, err = http.Get(apiURL + "/incidents")
		if err != nil {
			msg.err = fmt.Errorf("failed to fetch incidents: %w", err)
			return msg
		}
		defer resp.Body.Close()

		body, err = io.ReadAll(resp.Body)
		if err != nil {
			msg.err = fmt.Errorf("failed to read incidents response: %w", err)
			return msg
		}

		if err := json.Unmarshal(body, &msg.incidents); err != nil {
			msg.err = fmt.Errorf("failed to parse incidents: %w", err)
			return msg
		}

		return msg
	}
}

func main() {
	p := tea.NewProgram(initialModel())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
}
