import {
	CCDPinIn,
	CCDPinOut,
	clearCorePeripherals,
	createReconciler,
} from "hertz";
import { ClearCore } from "llamajet-driver-ts";
import { useState } from "react";
import { SerialPort } from "serialport";

// Follow makes digital pin 1 output follow the value of digital pin 0.
const Follow = () => {
	const [value, setValue] = useState(false);

	return (
		<>
			<CCDPinIn pin={0} onValueChange={setValue} />
			<CCDPinOut pin={1} value={value} />
		</>
	);
};

async function main() {
	// Create a new ClearCore instance and connect to it.
	const clearcore = new ClearCore(
		new SerialPort({
			path: "/dev/ttyACM0",
			baudRate: 115200,
		}),
	);
	await clearcore.connect();

	// Initialize the reconciler.
	const { render, runEventLoop } = createReconciler(
		clearCorePeripherals,
		clearcore,
	);

	// Render and run the event loop.
	render(<Follow />);
	await runEventLoop();
}

void main();
