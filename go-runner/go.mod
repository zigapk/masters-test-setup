module go-runner

go 1.24.0

require github.com/llamajet/llamajet-driver v0.0.0-20240604103621-4cc6468101e1

require (
	github.com/tarm/serial v0.0.0-20180830185346-98f6abe2eb07 // indirect
	golang.org/x/sys v0.6.0 // indirect
)

replace github.com/llamajet/llamajet-driver => ../llamajet-driver
