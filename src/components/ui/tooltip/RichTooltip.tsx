
import React, { useState } from 'react';

interface RichTooltipProps {
    content: React.ReactNode;
    children: React.ReactNode;
}

export const RichTooltip: React.FC<RichTooltipProps> = ({ content, children }) => {
    const [isVisible, setIsVisible] = useState(false);

    return (
        <div
            className="relative flex flex-col items-center"
            onMouseEnter={() => setIsVisible(true)}
            onMouseLeave={() => setIsVisible(false)}
        >
            {children}

            {isVisible && (
                <div className="absolute bottom-full mb-2 w-48 p-3 bg-gray-900 border border-gray-700 text-xs text-gray-300 rounded-lg shadow-xl z-50 animate-in fade-in zoom-in-95 duration-200">
                    {/* Arrow */}
                    <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-[1px] border-4 border-transparent border-t-gray-700"></div>
                    <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-[2px] border-4 border-transparent border-t-gray-900"></div>

                    {content}
                </div>
            )}
        </div>
    );
};
