# Advanced Queuing

![british queueing meme](https://y.yarn.co/276d8bc3-5a86-4b5c-ace4-99b363f9c43b_text.gif)

In the [quickstart](/getting-started/) we covered the basics of adding prints to the queue and running them, but you can do much more once you understand the nested structure of the print queue.

## Sets and Jobs

The queue is actually made up of two levels: sets and jobs.

**Sets** are a single print file, printed one or more times. You created a set by following the "Add prints to the queue" step in the [quickstart](/getting-started/).

**Jobs** are a collection of sets, printed one or more times. Jobs are always printed sequentially, from the top of the queue to the bottom.

## "Add" behavior

By default, every print file you add (as a set) is appended to a default, unnamed job at the end of the queue.

If you give this job a name (by clicking the title box, typing a name, then hitting enter or clicking away) it will stop collecting new prints and a new default job will be created when the next print is added.

## Example 1: Batched strategy

Let's consider an empty queue. If you add `A.gcode` with 5 copies and `B.gcode` with 5 copies, the print order will be:

`AAAAA BBBBB`

This is great if you want all of your `A` files to print before all your `B` files, for instance when you're working on a project that uses `A` but plan use `B` for something later. 

## Example 2: Interleaved strategy

Let's start again with an empty queue, but now suppose we add `A.gcode` with 1 copy, `B.gcode` with 1 copy, then set the job count to `5`. The print order will now be:

`AB AB AB AB AB`

This is exactly the pattern you would want if you were, for example, printing a box with `A.gcode` as the base and `B.gcode` as the lid. Each box would be completed in order, so you can use the first box without waiting for all the bases to print, then for the first lid to print.

## Example 3: Combined strategy

From an empty queue, you could even add `A.gcode` with 1 copy and `B.gcode` with 4 copies, and set the job count to `3`. The outcome is then:

`ABBBB ABBBB ABBBB`

We're simply mixing examples 1 and 2 together, but this would be ideal for a base print with multiple smaller additions - a table with four legs, for instance.

## Drag and drop reordering

At any time, you can click and drag jobs and sets with the grips on the left (the two vertical lines):

* Dragging a job reorders it among the jobs in the queue.
* Dragging a set reorders it within a job.

!!! tip

    You can also drag a set from one job to another! Note however that this may change the total number of that file printed if the destination job has a different count than the origin job.
