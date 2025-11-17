package common

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
)

// GenerateID generates a random hex ID
func GenerateID(prefix string) string {
	b := make([]byte, 8)
	rand.Read(b)
	return fmt.Sprintf("%s_%s", prefix, hex.EncodeToString(b))
}
