


export const MasterTimeline = ({ currentYear, onYearChange }: any) => {
    return (
        <div className="p-4 bg-gray-800 rounded">
            <h3>Timeline (Stub)</h3>
            <button onClick={() => onYearChange(currentYear - 1)}>-</button>
            <span>{currentYear}</span>
            <button onClick={() => onYearChange(currentYear + 1)}>+</button>
        </div>
    );
};
