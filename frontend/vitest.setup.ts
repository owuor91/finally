import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollIntoView; components call it on mount.
Element.prototype.scrollIntoView = () => {};
