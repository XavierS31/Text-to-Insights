package main

import (
	"context"
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime/debug"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/ledongthuc/pdf" // go get github.com/ledongthuc/pdf
)

type PDFResult struct {
	Path string
	Text string
	Err  error
}

func openAndExtractText(path string) (string, error) {
	f, r, err := pdf.Open(path)
	if err != nil {
		return "", err // throw error if file is corrupt/not openable
	}
	defer f.Close()

	textReader, err := r.GetPlainText()
	if err != nil {
		return "", err
	}

	data, err := io.ReadAll(textReader)
	if err != nil {
		return "", err
	}

	return string(data), nil
}

func extractWithTimeout(path string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	resultChan := make(chan struct {
		text string
		err  error
	}, 1)

	go func() {
		text, err := openAndExtractText(path) //extract the text from pdf
		resultChan <- struct {
			text string
			err  error
		}{text, err}
	}()

	select {
	case <-ctx.Done():
		return "", nil // too long to extract so save the system
	case res := <-resultChan:
		return res.text, res.err
	}
}

func pdfExtractionWorker(id int, jobs <-chan string, results chan<- PDFResult, wg *sync.WaitGroup) {
	defer wg.Done()
	defer func() {
		if r := recover(); r != nil {
			debug.PrintStack()
		}
	}()

	for path := range jobs {
		fmt.Printf("channel %d currently on %s\n", id, path)
		text, err := extractWithTimeout(path, 20*time.Second)
		if err == nil {
			text = strings.ReplaceAll(text, "\n", " ")
		}
		results <- PDFResult{Path: path, Text: text, Err: err}
	}
}

func main() {
	defer func() {
		if r := recover(); r != nil {
			// handle fatal crash
			debug.PrintStack()
		}
	}()

	pdfDir := "Photovoltaic-Cells-PDFs" //pdf with path, can go through subfolders
	csvFile := "extracted_texts.csv"    // whatever name you want the csv to be

	outFile, err := os.Create(csvFile)
	if err != nil {
		return
	}
	defer outFile.Close()

	writer := csv.NewWriter(outFile)
	defer func() {
		writer.Flush()
	}()
	writer.Write([]string{"file_path", "text"})

	var pdfPaths []string
	err = filepath.WalkDir(pdfDir, func(path string, d os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return nil
		}
		if d != nil && !d.IsDir() && strings.HasSuffix(strings.ToLower(d.Name()), ".pdf") {
			pdfPaths = append(pdfPaths, path)
		}
		return nil
	})
	if err != nil {
		return
	}

	sort.Strings(pdfPaths)
	const maxWorkers = 4
	jobs := make(chan string, len(pdfPaths))
	results := make(chan PDFResult, len(pdfPaths))

	var wg sync.WaitGroup
	for i := 1; i <= maxWorkers; i++ {
		wg.Add(1)
		go pdfExtractionWorker(i, jobs, results, &wg)
	}

	for _, path := range pdfPaths {
		jobs <- path
	}
	close(jobs)

	go func() {
		wg.Wait()
		close(results) //close channel
	}()

	resultMap := make(map[string]PDFResult)
	for res := range results {
		if res.Err != nil {
			continue
		}
		resultMap[res.Path] = res
	}

	var sortedPaths []string
	for path := range resultMap {
		sortedPaths = append(sortedPaths, path)
	}
	sort.Strings(sortedPaths) //sorted the paths alphabetically

	count := 0
	for _, path := range sortedPaths {
		res := resultMap[path]
		err := writer.Write([]string{res.Path, res.Text})
		if err == nil {
			count++
		}
	}

	fmt.Printf("\n all done %d %s\n", count, csvFile)
}
