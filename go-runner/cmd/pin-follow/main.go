package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	driver "github.com/llamajet/llamajet-driver"
	"github.com/llamajet/llamajet-driver/clearcore"
)

const (
	inputPin  = 0
	outputPin = 1
	firstPin  = 2
	lastPin   = 8
)

func main() {
	var (
		n      int
		nSet   bool
		serial = flag.String("serial", "/dev/ttyACM0", "serial device path")
		baud   = flag.Int("baud", 115200, "serial baud rate")
		detail = flag.Bool("verbose", false, "print per-interval benchmark numbers")
	)

	flag.Func("n", "number of digital input reads from pins 2..8; pins are repeated when count exceeds 7", func(v string) error {
		parsed, err := strconv.Atoi(v)
		if err != nil {
			return err
		}
		n = parsed
		nSet = true
		return nil
	})

	flag.Usage = func() {
		_, _ = fmt.Fprintf(flag.CommandLine.Output(), "Usage: pin-follow -n <count> [-serial /dev/ttyACM0] [-baud 115200] [-verbose]\n")
		flag.PrintDefaults()
	}

	flag.Parse()

	if !nSet {
		flag.Usage()
		log.Fatal("missing required -n argument")
	}

	if n < 0 {
		log.Fatal("n must be >= 0")
	}

	maxInputs := lastPin - firstPin + 1

	driverConn, err := clearcore.New(*serial, *baud)
	if err != nil {
		log.Fatal(err)
	}

	cleanup := func() {
		_ = driverConn.WriteDigitalPins(driver.DigitalPinWriteParameters{
			ID:    outputPin,
			Value: false,
		})
	}
	defer cleanup()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err = driverConn.SetPinsMode(driver.PinModeDigitalOutput, outputPin); err != nil {
		log.Fatal(err)
	}

	randomInputs := make([]int, maxInputs)
	for i := range maxInputs {
		randomInputs[i] = firstPin + i
	}

	rand.Seed(time.Now().UnixNano())

	rand.Shuffle(len(randomInputs), func(i, j int) {
		randomInputs[i], randomInputs[j] = randomInputs[j], randomInputs[i]
	})

	inputPins := make([]int, 0, n+1)
	configuredPins := map[int]struct{}{inputPin: struct{}{}}
	inputPins = append(inputPins, inputPin)

	for i := 0; i < n; i++ {
		pin := randomInputs[i%maxInputs]
		inputPins = append(inputPins, pin)
		configuredPins[pin] = struct{}{}
	}

	pinsToConfigure := make([]int, 0, len(configuredPins))
	for pin := range configuredPins {
		pinsToConfigure = append(pinsToConfigure, pin)
	}

	if err = driverConn.SetPinsMode(driver.PinModeDigitalInput, pinsToConfigure...); err != nil {
		log.Fatal(err)
	}

	err = driverConn.WriteDigitalPins(driver.DigitalPinWriteParameters{
		ID:    outputPin,
		Value: false,
	})
	if err != nil {
		log.Fatal(err)
	}

	var (
		iterations uint64
		reads      uint64
		writes     uint64
		start      = time.Now()
		lastReport = time.Now()
	)

	for {
		if ctx.Err() != nil {
			fmt.Printf("iterations=%d reads=%d writes=%d\n", iterations, reads, writes)
			return
		}

		if err = singleIteration(driverConn, inputPins, &iterations, &reads, &writes); err != nil {
			log.Fatal(err)
		}

		if *detail {
			if elapsed := time.Since(lastReport); elapsed >= time.Second {
				totalElapsed := time.Since(start).Seconds()
				fmt.Printf(
					"iters=%d reads=%d writes=%d | total=%.2fs | %.2f iter/s %.2f read/s %.2f write/s\n",
					iterations,
					reads,
					writes,
					totalElapsed,
					float64(iterations)/totalElapsed,
					float64(reads)/totalElapsed,
					float64(writes)/totalElapsed,
				)
				lastReport = time.Now()
			}
		}
	}
}

func singleIteration(
	d *clearcore.Driver,
	pins []int,
	iterations *uint64,
	reads *uint64,
	writes *uint64,
) error {
	for _, pin := range pins {
		vals, err := d.ReadDigitalSensors(pin)
		if err != nil {
			return err
		}
		if len(vals) != 1 {
			return fmt.Errorf("unexpected digital read result length for pin %d", pin)
		}
		(*reads)++

		if pin != inputPin {
			continue
		}

		err = d.WriteDigitalPins(driver.DigitalPinWriteParameters{
			ID:    outputPin,
			Value: vals[0],
		})
		if err != nil {
			return err
		}

		(*writes)++
	}

	(*iterations)++
	return nil
}
