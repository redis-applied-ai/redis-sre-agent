import type { Meta, StoryObj } from "@storybook/react";
import { Pagination } from "./Pagination";

const meta = {
  title: "Components/Pagination",
  component: Pagination,
  parameters: {
    layout: "fullwidth",
  },
  tags: ["autodocs"],
  argTypes: {
    currentPage: { control: { type: "number", min: 1 } },
    totalPages: { control: { type: "number", min: 1 } },
    itemCount: { control: { type: "number", min: 0 } },
    pageSize: { control: { type: "number", min: 1 } },
    showPageSizeSelector: { control: "boolean" },
    showPageInput: { control: "boolean" },
  },
} satisfies Meta<typeof Pagination>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    currentPage: 1,
    totalPages: 10,
    itemCount: 250,
    pageSize: 25,
    itemLabel: "deployments",
    onPageChange: (page) => console.log("Page changed to:", page),
    onPageSizeChange: (size) => console.log("Page size changed to:", size),
  },
};

export const FirstPage: Story = {
  args: {
    currentPage: 1,
    totalPages: 5,
    itemCount: 50,
    pageSize: 10,
    itemLabel: "items",
    onPageChange: (page) => console.log("Page changed to:", page),
    onPageSizeChange: (size) => console.log("Page size changed to:", size),
  },
};

export const LastPage: Story = {
  args: {
    currentPage: 5,
    totalPages: 5,
    itemCount: 50,
    pageSize: 10,
    itemLabel: "items",
    onPageChange: (page) => console.log("Page changed to:", page),
    onPageSizeChange: (size) => console.log("Page size changed to:", size),
  },
};

export const MiddlePage: Story = {
  args: {
    currentPage: 7,
    totalPages: 15,
    itemCount: 150,
    pageSize: 10,
    itemLabel: "results",
    onPageChange: (page) => console.log("Page changed to:", page),
    onPageSizeChange: (size) => console.log("Page size changed to:", size),
  },
};

export const WithoutPageSizeSelector: Story = {
  args: {
    currentPage: 3,
    totalPages: 8,
    itemCount: 80,
    showPageSizeSelector: false,
    itemLabel: "users",
    onPageChange: (page) => console.log("Page changed to:", page),
  },
};

export const WithoutPageInput: Story = {
  args: {
    currentPage: 2,
    totalPages: 4,
    itemCount: 40,
    showPageInput: false,
    itemLabel: "records",
    onPageChange: (page) => console.log("Page changed to:", page),
    onPageSizeChange: (size) => console.log("Page size changed to:", size),
  },
};

export const CustomPageSizes: Story = {
  args: {
    currentPage: 1,
    totalPages: 20,
    itemCount: 500,
    pageSize: 25,
    pageSizeOptions: [5, 10, 25, 50, 100],
    itemLabel: "entries",
    onPageChange: (page) => console.log("Page changed to:", page),
    onPageSizeChange: (size) => console.log("Page size changed to:", size),
  },
};
