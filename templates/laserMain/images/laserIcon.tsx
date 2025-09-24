import React from "react";

interface CustomIconProps {
  size?: number;        // размер иконки
  color?: string;       // цвет обводки
  strokeWidth?: number; // толщина линии
}

const LaserIcon: React.FC<CustomIconProps> = ({
  size = 36,
  color = "white",
  strokeWidth = 1.5,
}) => {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      role="img"
      width={size}
      height={size}
      viewBox="0 0 36 36"
    >
      <path
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        d="M8 24H16M15 9 V18L19 23  23 18 V17 L15 17M23 9V18L19 23 19 24 30 24"
      />
    </svg>
  );
};

export default LaserIcon;
