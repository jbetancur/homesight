package common

import "time"

// Retry executes a function with exponential backoff
func Retry(attempts int, sleep time.Duration, fn func() error) error {
	if err := fn(); err != nil {
		if attempts--; attempts > 0 {
			time.Sleep(sleep)
			return Retry(attempts, sleep*2, fn)
		}
		return err
	}
	return nil
}
