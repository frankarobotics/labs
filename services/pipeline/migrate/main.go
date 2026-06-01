package main

import (
	"database/sql"
	"flag"
	"fmt"
	"io/fs"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/golang-migrate/migrate/v4"
	"github.com/golang-migrate/migrate/v4/database/postgres"
	_ "github.com/golang-migrate/migrate/v4/source/file"
	_ "github.com/lib/pq"
)

// migrateLogger implements migrate.Logger to log each migration step, including filename
type migrateLogger struct {
	versionToFile map[uint]string
	mu            sync.Mutex
}

func (l *migrateLogger) Printf(format string, v ...interface{}) {
	msg := fmt.Sprintf(format, v...)
	// Look for lines like "up 1" or "down 2"
	re := regexp.MustCompile(`\b(up|down) (\d+)`)
	matches := re.FindStringSubmatch(msg)
	if len(matches) == 3 {
		direction := matches[1]
		version := matches[2]
		var verUint uint
		fmt.Sscanf(version, "%d", &verUint)
		l.mu.Lock()
		fname := l.versionToFile[verUint]
		l.mu.Unlock()
		if fname != "" {
			log.Printf("[%s] Applying migration: %s", strings.ToUpper(direction), fname)
		} else {
			log.Printf("[%s] Applying migration version: %s", strings.ToUpper(direction), version)
		}
	}
	log.Printf("%s", msg)
}

func (l *migrateLogger) Verbose() bool {
	return true
}

func main() {
	// Parse CLI arguments
	flag.Usage = func() {
		fmt.Fprintf(flag.CommandLine.Output(), "Usage: %s [up|down|goto <version>]\n", os.Args[0])
		flag.PrintDefaults()
	}
	flag.Parse()
	args := flag.Args()

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("DATABASE_URL environment variable is required")
	}

	log.Printf("Connecting to database...")

	// Wait for database to be available
	var db *sql.DB
	var err error
	maxWait := 60 // seconds
	for i := 0; i < maxWait; i++ {
		db, err = sql.Open("postgres", dbURL)
		if err == nil {
			err = db.Ping()
			if err == nil {
				log.Printf("Database is available (after %d seconds)", i+1)
				break
			}
		}
		log.Printf("Waiting for database to be available... (%d/%d)", i+1, maxWait)
		if db != nil {
			db.Close()
		}
		time.Sleep(1 * time.Second)
	}
	if err != nil {
		log.Fatalf("Database not available after %d seconds: %v", maxWait, err)
	}
	defer db.Close()

	log.Printf("Starting migration from /workspace/migrations ...")
	driver, err := postgres.WithInstance(db, &postgres.Config{})
	if err != nil {
		log.Fatalf("Failed to create postgres driver: %v", err)
	}

	// Map migration version to filename
	migrationsDir := "/workspace/migrations"
	versionToFile := make(map[uint]string)
	fileRe := regexp.MustCompile(`^(\d+)_.*\.(up|down)\.sql$`)
	_ = filepath.WalkDir(migrationsDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		base := filepath.Base(path)
		matches := fileRe.FindStringSubmatch(base)
		if len(matches) == 3 {
			var ver uint
			fmt.Sscanf(matches[1], "%d", &ver)
			// Only map the up migration file for logging
			if matches[2] == "up" {
				versionToFile[ver] = base
			}
		}
		return nil
	})

	m, err := migrate.NewWithDatabaseInstance(
		"file:///workspace/migrations",
		"postgres", driver,
	)
	if err != nil {
		log.Fatalf("Failed to create migrate instance: %v", err)
	}

	// Set logger to print each migration step with filename
	m.Log = &migrateLogger{versionToFile: versionToFile}

	// Determine migration action
	action := "up"
	var gotoVersion uint
	if len(args) > 0 {
		switch strings.ToLower(args[0]) {
		case "up":
			action = "up"
		case "down":
			action = "down"
		case "goto":
			if len(args) < 2 {
				log.Fatalf("Usage: %s goto <version>", os.Args[0])
			}
			action = "goto"
			_, err := fmt.Sscanf(args[1], "%d", &gotoVersion)
			if err != nil {
				log.Fatalf("Invalid version for goto: %v", err)
			}
		default:
			log.Fatalf("Unknown command: %s", args[0])
		}
	}

	switch action {
	case "up":
		log.Printf("Migrating up to latest...")
		if err := m.Up(); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("Migration failed: %v", err)
		}
		log.Printf("Migrations applied successfully!")
	case "down":
		log.Printf("Reverting last migration...")
		if err := m.Steps(-1); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("Down migration failed: %v", err)
		}
		log.Printf("Down migration applied successfully!")
	case "goto":
		log.Printf("Migrating to version %d...", gotoVersion)
		if err := m.Migrate(gotoVersion); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("Goto migration failed: %v", err)
		}
		log.Printf("Migration to version %d applied successfully!", gotoVersion)
	}
}
