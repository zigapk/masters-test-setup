import { CCDPinIn } from "hertz";

const MIN_PIN_ID = 2; // Pins 0 and 1 are reserved for estop and dangerous output
const MAX_PIN_ID = 8; // Highest pin ID is 8 on the default CC board

export const FluffNode = ({ pin }: { pin: number }) => {
	return <CCDPinIn pin={pin} onValueChange={() => {}} />;
};

// Creates a shallow tree with N digital input nodes on a single level.
export const ShallowFluff = ({ n }: { n: number }) => {
	return (
		<>
			{Array.from({ length: n }, (_, i) => i).map((i) => {
				// A digital input node that does nothing
				const pin = (i % (MAX_PIN_ID - MIN_PIN_ID)) + MIN_PIN_ID;
				return <CCDPinIn key={i} pin={pin} onValueChange={() => {}} />;
			})}
		</>
	);
};

// Creates a deep tree with N digital input nodes in a single deep branch with input pin nodes hangin off each node.
// Essentially renders the component recursively until reaching n == 0.
export const DeepFluff = ({
	n,
	i,
	childAtIthPosition,
}: {
	n: number;
	i?: number;
	childAtIthPosition?: React.ReactNode;
}) => {
	// We reached the end of the tree.
	if (n === 0) {
		return <></>;
	}

	// Place the special child at the ith position.
	if (i != null && i === n && childAtIthPosition != null) {
		return (
			<>
				{childAtIthPosition}
				{/* Recursively render the rest of the tree without subtracting 1 from n. */}
				<DeepFluff n={n} />
			</>
		);
	}

	// Determine the pin index that is to be used.
	const pin = (n % (MAX_PIN_ID - MIN_PIN_ID)) + MIN_PIN_ID;
	// Render the input node and recursively render the rest of the tree.
	return (
		<>
			<CCDPinIn pin={pin} onValueChange={() => {}} />
			{<DeepFluff n={n - 1} />}
		</>
	);
};
