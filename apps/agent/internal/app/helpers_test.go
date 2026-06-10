package app

import (
	"os"
	"strings"
)

func readFileString(path string) (string, error) {
	b, err := os.ReadFile(path)
	return string(b), err
}

func contains(haystack, needle string) bool {
	return strings.Contains(haystack, needle)
}
