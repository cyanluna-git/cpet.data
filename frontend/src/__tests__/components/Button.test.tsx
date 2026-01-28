import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '@/components/ui/button';

describe('Button', () => {
  it('renders with children', () => {
    render(<Button>클릭</Button>);
    expect(screen.getByText('클릭')).toBeInTheDocument();
  });

  it('renders as a button element by default', () => {
    render(<Button>버튼</Button>);
    const button = screen.getByRole('button', { name: '버튼' });
    expect(button.tagName).toBe('BUTTON');
  });

  it('handles click events', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>클릭</Button>);

    fireEvent.click(screen.getByText('클릭'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('handles multiple clicks', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>클릭</Button>);

    const button = screen.getByText('클릭');
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);
    expect(handleClick).toHaveBeenCalledTimes(3);
  });

  it('can be disabled', () => {
    const handleClick = vi.fn();
    render(
      <Button disabled onClick={handleClick}>
        클릭
      </Button>
    );

    const button = screen.getByText('클릭');
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(handleClick).not.toHaveBeenCalled();
  });

  it('renders with default variant and has proper styling classes', () => {
    render(<Button>기본</Button>);
    const button = screen.getByText('기본');
    // Button has data-slot attribute for styling
    expect(button).toHaveAttribute('data-slot', 'button');
    // Has base button classes
    expect(button.className).toContain('inline-flex');
  });

  it('renders different variants', () => {
    const { rerender } = render(<Button variant="ghost">고스트</Button>);
    expect(screen.getByText('고스트')).toBeInTheDocument();

    rerender(<Button variant="outline">아웃라인</Button>);
    expect(screen.getByText('아웃라인')).toBeInTheDocument();

    rerender(<Button variant="destructive">삭제</Button>);
    expect(screen.getByText('삭제')).toBeInTheDocument();

    rerender(<Button variant="secondary">세컨더리</Button>);
    expect(screen.getByText('세컨더리')).toBeInTheDocument();

    rerender(<Button variant="link">링크</Button>);
    expect(screen.getByText('링크')).toBeInTheDocument();
  });

  it('renders with different sizes', () => {
    const { rerender } = render(<Button size="sm">Small</Button>);
    expect(screen.getByText('Small')).toBeInTheDocument();

    rerender(<Button size="lg">Large</Button>);
    expect(screen.getByText('Large')).toBeInTheDocument();

    rerender(<Button size="icon">I</Button>);
    expect(screen.getByText('I')).toBeInTheDocument();

    rerender(<Button size="default">Default</Button>);
    expect(screen.getByText('Default')).toBeInTheDocument();
  });

  it('renders as child element when asChild is true', () => {
    render(
      <Button asChild>
        <a href="/test">링크 버튼</a>
      </Button>
    );

    const link = screen.getByText('링크 버튼');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/test');
  });

  it('applies custom className', () => {
    render(<Button className="custom-class">커스텀</Button>);
    expect(screen.getByText('커스텀')).toHaveClass('custom-class');
  });

  it('forwards ref correctly', () => {
    const ref = vi.fn();
    render(<Button ref={ref}>Ref 테스트</Button>);
    expect(ref).toHaveBeenCalled();
  });

  it('supports type attribute', () => {
    const { rerender } = render(<Button type="submit">제출</Button>);
    expect(screen.getByText('제출')).toHaveAttribute('type', 'submit');

    rerender(<Button type="reset">리셋</Button>);
    expect(screen.getByText('리셋')).toHaveAttribute('type', 'reset');

    rerender(<Button type="button">버튼</Button>);
    expect(screen.getByText('버튼')).toHaveAttribute('type', 'button');
  });

  it('passes additional props to button element', () => {
    render(
      <Button data-testid="test-button" aria-label="테스트 버튼">
        버튼
      </Button>
    );
    const button = screen.getByTestId('test-button');
    expect(button).toHaveAttribute('aria-label', '테스트 버튼');
  });
});
