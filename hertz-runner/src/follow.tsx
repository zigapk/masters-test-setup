import { Command, Option } from "commander";
import {
	CCDPinIn,
	CCDPinOut,
	clearCorePeripherals,
	createReconciler,
} from "hertz";
import { ClearCore } from "llamajet-driver-ts";
import { useState } from "react";
import { SerialPort } from "serialport";
import { DeepFluff, ShallowFluff } from "./fluff";

// Follow makes digital pin 1 output follow the value of digital pin 0 using pin input and output nodes.
const Follow = () => {
	const [value, setValue] = useState(false);

	return (
		<>
			<CCDPinIn pin={0} onValueChange={setValue} />
			<CCDPinOut pin={1} value={value} />
		</>
	);
};

const FollowWithShallowFluff = ({ n }: { n: number }) => {
	return (
		<>
			<Follow />
			<ShallowFluff n={n} />
		</>
	);
};

const FollowWithDeepFluff = ({ n }: { n: number }) => {
	return (
		<>
			<Follow />
			<DeepFluff n={n} />
		</>
	);
};

async function main() {
	const program = new Command();
	program
		.requiredOption("-n, --n <number>", "value to pass to fluff components", parseInt)
		.addOption(
			new Option("-f, --fluff-type <type>", "fluff type: deep or shallow")
				.choices(["deep", "shallow"])
				.makeOptionMandatory(),
		);
	program.parse();
	const options = program.opts();
	// biome-ignore lint/complexity/useLiteralKeys: Either way is fine.
	const n = options["n"];
	// biome-ignore lint/complexity/useLiteralKeys: Either way is fine.
	const fluffType = options["fluffType"];

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
	const component =
		fluffType === "shallow" ? (
			<FollowWithShallowFluff n={n} />
		) : (
			<FollowWithDeepFluff n={n} />
		);
	render(component);
	await runEventLoop();
}

void main();
