


export const Button = ({ children, onClick, className, disabled }: any) => {
    return (
        <button onClick={onClick} className={className} disabled={disabled}>
            {children}
        </button>
    );
};
