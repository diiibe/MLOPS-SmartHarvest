
import * as React from "react"
import { format, isAfter, isBefore } from "date-fns"
import { Calendar as CalendarIcon, Check } from "lucide-react"
import type { DateRange } from "react-day-picker"
import { it } from "date-fns/locale"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"

interface DateRangePickerProps {
    date: DateRange | undefined
    setDate: (date: DateRange | undefined) => void
    onApply: () => void
    loading?: boolean
}

const MIN_DATE = new Date(2018, 0, 1)
const MAX_DATE = new Date() // Today

export function DateRangePicker({
    date,
    setDate,
    onApply,
}: DateRangePickerProps) {
    const [tempDate, setTempDate] = React.useState<DateRange | undefined>(date)
    const [isOpen, setIsOpen] = React.useState(false)

    // Sync temp state when opening
    React.useEffect(() => {
        if (isOpen) {
            setTempDate(date)
        }
    }, [isOpen, date])

    const handleYearClick = (year: number) => {
        const start = new Date(year, 0, 1)
        let end = new Date(year, 11, 31)

        // Cap at max date if current year
        if (isAfter(end, MAX_DATE)) {
            end = MAX_DATE
        }

        const newRange = { from: start, to: end }
        setTempDate(newRange)
    }

    const handleApply = () => {
        setDate(tempDate)
        setIsOpen(false)
        onApply()
    }

    const years = Array.from(
        { length: MAX_DATE.getFullYear() - MIN_DATE.getFullYear() + 1 },
        (_, i) => MIN_DATE.getFullYear() + i
    )

    return (
        <div className="grid gap-2">
            <Popover open={isOpen} onOpenChange={setIsOpen}>
                <PopoverTrigger asChild>
                    <Button
                        id="date"
                        variant={"outline"}
                        className={cn(
                            "w-[300px] justify-start text-left font-normal bg-card/50 backdrop-blur-sm border-white/10 hover:bg-white/5 hover:text-white transition-all",
                            !date && "text-muted-foreground"
                        )}
                    >
                        <CalendarIcon className="mr-2 h-4 w-4" />
                        {date?.from ? (
                            date.to ? (
                                <>
                                    {format(date.from, "dd MMM yyyy", { locale: it })} -{" "}
                                    {format(date.to, "dd MMM yyyy", { locale: it })}
                                </>
                            ) : (
                                format(date.from, "dd MMM yyyy", { locale: it })
                            )
                        ) : (
                            <span>Seleziona periodo</span>
                        )}
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                    <div className="flex">
                        {/* Year Timeline Shortcut */}
                        <div className="border-r p-2 flex flex-col gap-1 w-[80px] overflow-y-auto max-h-[350px]">
                            <span className="text-xs font-semibold text-muted-foreground px-2 mb-2">Anni</span>
                            {years.map((year) => (
                                <Button
                                    key={year}
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleYearClick(year)}
                                    className={cn(
                                        "justify-start text-xs",
                                        tempDate?.from?.getFullYear() === year && "bg-accent text-accent-foreground"
                                    )}
                                >
                                    {year}
                                </Button>
                            ))}
                        </div>

                        <div className="p-0">
                            <Calendar
                                initialFocus
                                mode="range"
                                defaultMonth={tempDate?.from}
                                selected={tempDate}
                                onSelect={setTempDate}
                                numberOfMonths={2}
                                disabled={(date) =>
                                    isAfter(date, MAX_DATE) || isBefore(date, MIN_DATE)
                                }
                                locale={it}
                                classNames={{
                                    day_selected: "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
                                }}
                            />
                            <div className="p-3 border-t flex justify-end bg-muted/20">
                                <Button
                                    size="sm"
                                    onClick={handleApply}
                                    disabled={!tempDate?.from || !tempDate?.to}
                                    className="gap-2"
                                >
                                    <Check className="h-4 w-4" />
                                    Applica Selezione
                                </Button>
                            </div>
                        </div>
                    </div>
                </PopoverContent>
            </Popover>
        </div>
    )
}
