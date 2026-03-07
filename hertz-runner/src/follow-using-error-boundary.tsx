import { Command, Option } from "commander";
import {
	CCDPinIn,
	CCDPinOut,
	clearCorePeripherals,
	createReconciler,
} from "hertz";
import { ClearCore } from "llamajet-driver-ts";
import { useEffect } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { SerialPort } from "serialport";
import { DeepFluff, ShallowFluff } from "./fluff";

// Fallback disables the output pin (1) and resets after 100ms
const Fallback = ({
	resetErrorBoundary,
}: {
	resetErrorBoundary: () => void;
}) => {
	useEffect(() => {
		const interval = setInterval(() => {
			resetErrorBoundary();
		}, 100);
		return () => clearInterval(interval);
	}, [resetErrorBoundary]);
	return <CCDPinOut pin={1} value={false} />;
};

// Follow makes digital pin 1 output follow the value of digital pin 0 using pin input and output nodes.
const FollowUsingErrorBoundary = ({
	children,
}: {
	children: React.ReactNode;
}) => {
	return (
		<ErrorBoundary FallbackComponent={Fallback}>
			{/* Set the value of the output pin to true when not inside the fallback component */}
			<CCDPinOut pin={1} value={true} />
			{children}
		</ErrorBoundary>
	);
};

const FollowWithShallowFluff = ({ n }: { n: number }) => {
	return (
		<FollowUsingErrorBoundary>
			<CCDPinIn
				pin={0}
				onValueChange={(value, isInitialRead) => {
					if (value === false && !isInitialRead) {
						throw new Error("Value is false - estop was pressed!");
					}
				}}
			/>
			<ShallowFluff n={n} />
		</FollowUsingErrorBoundary>
	);
};

const FollowWithDeepFluff = ({ n, i }: { n: number; i: number }) => {
	return (
		<FollowUsingErrorBoundary>
			<DeepFluff
				n={n}
				i={i}
				childAtIthPosition={
					<CCDPinIn
						pin={0}
						onValueChange={(value, isInitialRead) => {
							if (value === false && !isInitialRead) {
								throw new Error("Value is false - estop was pressed!");
							}
						}}
					/>
				}
			/>
		</FollowUsingErrorBoundary>
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
		)
		.option("-i, --i <number>", "value for deep fluff (required when fluff-type is deep)", parseInt);
	program.parse();
	const options = program.opts();
	// biome-ignore lint/complexity/useLiteralKeys: Either way is fine.
	const n = options["n"];
	// biome-ignore lint/complexity/useLiteralKeys: Either way is fine.
	const fluffType = options["fluffType"];
	// biome-ignore lint/complexity/useLiteralKeys: Either way is fine.
	const i = options["i"];

	if (fluffType === "deep" && i === undefined) {
		console.error("Error: --i is required when --fluff-type is 'deep'");
		process.exit(1);
	}

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
			<FollowWithDeepFluff n={n} i={i} />
		);
	render(component);
	await runEventLoop();
}

void main();
