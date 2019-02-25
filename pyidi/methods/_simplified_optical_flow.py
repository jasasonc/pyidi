import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from scipy.signal import convolve2d
from tqdm import tqdm
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


from .idi_method import IDIMethod


class SimplifiedOpticalFlow(IDIMethod):
    """Displacmenet computation based on Simplified Optical Flow method [1].

    Literature:
        [1] Javh, J., Slavič, J., & Boltežar, M. (2017). The subpixel resolution 
            of optical-flow-based modal analysis. Mechanical Systems 
            and Signal Processing, 88, 89–99.
        [2] Lucas, B. D., & Kanade, T. (1981). An Iterative Image Registration 
            Technique with an Application to Stereo Vision. In Proceedings of 
            the 7th International Joint Conference on Artificial 
            Intelligence - Volume 2 (pp. 674–679). San Francisco, CA, 
            USA: Morgan Kaufmann Publishers Inc.
    """

    def __init__(self, video, **kwargs):
        """
        :param video: 'parent' object
        :param kwargs: keyword arguments (defined in `options`)
        """
        options = {
            'subset_size': 3,               # Size of the smoothing filter
            'pixel_shift': False,           # Pixel shifting (not implemented!)
            'convert_from_px': 1,           # Convert from pixels to other unit
            'mraw_range': 'all',            # Range of frames for displacement identification
            'mean_n_neighbours': 0,         # Average the neigbouring pixel displacements
            'zero_shift': False,            # Shift the mean of the signal to zero
            'progress_bar': True,           # Show progress bar
            'reference_range': (0, 100),    # Averaging range for reference image
        }

        # Change docstring (add kwargs documentation) in pyIDI.set_method
        self.change_docstring(video.set_method, options)

        # Check for valid kwargs
        self.check_kwargs(kwargs, options)

        options.update(kwargs) # Update the options dict
        self.__dict__.update(options) # Update the objects attributes

        # Get reference image and gradients
        self.reference_image, self.gradient_0, self.gradient_1, self.gradient_magnitude = self.reference(
            video.mraw[self.reference_range[0]: self.reference_range[1]], self.subset_size)

    def calculate_displacements(self, video):
        if not hasattr(video, 'points'):
            raise Exception('Please set points for analysis!')

        self.displacements = np.zeros((video.points.shape[0], video.N, 2))
        latest_displacements = 0

        gradient_0_direction = np.copy(self.gradient_0)
        gradient_1_direction = np.copy(self.gradient_1)

        signs_0 = np.sign(
            gradient_0_direction[video.points[:, 0], video.points[:, 1]])
        signs_1 = np.sign(
            gradient_1_direction[video.points[:, 0], video.points[:, 1]])

        self.direction_correction_0 = np.abs(
            gradient_0_direction[video.points[:, 0], video.points[:, 1]] / self.gradient_magnitude[video.points[:, 0], video.points[:, 1]])
        self.direction_correction_1 = np.abs(
            gradient_1_direction[video.points[:, 0], video.points[:, 1]] / self.gradient_magnitude[video.points[:, 0], video.points[:, 1]])

        # limited range of mraw can be observed
        if self.mraw_range != 'all':
            limited_mraw = video.mraw[self.mraw_range[0]: self.mraw_range[1]]
        else:
            limited_mraw = video.mraw

        # Progress bar
        if self.progress_bar:
            p_bar = tqdm
        else:
            p_bar = lambda x: x # empty function

        # calculating the displacements
        for i, image in enumerate(p_bar(limited_mraw)):
            image_filtered = self.subset(image, self.subset_size)

            if self.pixel_shift:
                print('Pixel-shifting is not yet implemented.')
                break

            else:
                self.image_roi = image_filtered[video.points[:, 0], video.points[:, 1]]

                self.latest_displacements = (self.reference_image[video.points[:, 0], video.points[:, 1]] - self.image_roi) / \
                    self.gradient_magnitude[video.points[:, 0], video.points[:, 1]]

            self.displacements[:, i, 0] = signs_0 * self.direction_correction_0 * \
                self.latest_displacements * self.convert_from_px
            self.displacements[:, i, 1] = signs_1 * self.direction_correction_1 * \
                self.latest_displacements * self.convert_from_px

        # average the neighbouring points
        if isinstance(self.mean_n_neighbours, int):
            if self.mean_n_neighbours > 0:
                self.displacement_averaging()

        # shift the mean of the signal to zero
        if isinstance(self.zero_shift, bool):
            if self.zero_shift is True:
                m = np.mean(self.displacements, axis=1)
                self.displacements[:, :, 0] -= m[:, 0:1]
                self.displacements[:, :, 1] -= m[:, 1:]

    def displacement_averaging(self):
        """Calculate the average of displacements.
        """
        print('Averaging...')
        kernel = np.ones((self.mean_n_neighbours, 1)) / self.mean_n_neighbours
        
        d_0 = convolve2d(self.displacements[:, :, 0], kernel, mode='valid')[::self.mean_n_neighbours]
        d_1 = convolve2d(self.displacements[:, :, 1], kernel, mode='valid')[::self.mean_n_neighbours]
        
        self.displacements = np.concatenate((d_0[:, :, np.newaxis], d_1[:, :, np.newaxis]), axis=2)
        print('Finished!')

    def pixel_shift(self):
        """Pixel shifting implementation.
        """
        pass

    def reference(self, images, subset_size):
        """Calculation of the reference image, image gradients and gradient amplitudes.

        :param images: Images to average. Usually the first 100 images.
        :param subset_size: Size of the subset to average.
        :return: Reference image, image gradient in 0 direction, image gradient in 1 direction, gradient magnitude
        """
        reference_image = np.mean([self.subset(image_, subset_size)
                                   for image_ in images], axis=0)

        gradient_0, gradient_1 = np.gradient(reference_image)
        gradient_magnitude = np.sqrt(gradient_0**2 + gradient_1**2)

        return reference_image, gradient_0, gradient_1, gradient_magnitude

    def subset(self, data, subset_size):
        """Calculating a filtered image.

        Calculates a filtered image with subset of d. It sums the area of d x d.

        :param data: Image that is to be filtered.
        :param subset_size: Size of the subset.
        :return: Filtered image.
        """
        subset_size_q = int((subset_size - 1) / 2)
        subset_image = []

        for i in range(-subset_size_q, subset_size_q + 1):
            for j in range(-subset_size_q, subset_size_q + 1):
                subset_roll = np.roll(data, i, axis=0)
                subset_roll = np.roll(subset_roll, j, axis=1)
                subset_image.append(subset_roll)

        return np.sum(np.asarray(subset_image), axis=0)

    @staticmethod
    def get_points(video, **kwargs):
        """Determine the points.
        """
        options = {
            'subset': (20, 20),
            'axis': None,
        }
        
        # Change the docstring in `set_points` to show the options
        docstring = video.set_points.__doc__.split('---')
        docstring[1] = '- ' + '\n\t- '.join(options) + '\n\t'
        video.set_points.__func__.__doc__ = '---\n\t'.join(docstring)

        options.update(kwargs)

        if isinstance(options['subset'], int):
            options['subset'] = 2*(options['subset'], )
        elif type(options['subset']) not in [list, tuple]:
            raise Exception(f'keyword argument "subset" must be int, list or tuple (not {type(options["subset"])})')

        polygon = PickPoints(video, subset=options['subset'], axis=options['axis'])


class PickPoints:
    """Pick the area of interest.

    Select the points with highest gradient in vertical direction.
    """

    def __init__(self, video, subset, axis):
        self.subset = subset
        self.axis = axis

        image = video.mraw[0]
        self.gradient_0, self.gradient_1 = np.gradient(image.astype(float))

        root = tk.Tk() # Tkinter
        root.title('Pick points') # Tkinter
        fig = Figure(figsize=(15, 7)) # Tkinter
        ax = fig.add_subplot(111) # Tkinter
        ax.grid(False)
        ax.imshow(image, cmap='gray')

        self.polygon = [[], []]
        line, = ax.plot(self.polygon[1], self.polygon[0], 'r.-')

        print('SHIFT + LEFT mouse button to pick a pole.\nRIGHT mouse button to erase the last pick.')

        self.shift_is_held = False
        def on_key_press(event):
            """Function triggered on key press (shift)."""
            if event.key == 'shift':
                self.shift_is_held = True
        
        def on_key_release(event):
            """Function triggered on key release (shift)."""
            if event.key == 'shift':
                self.shift_is_held = False

        def onclick(event):
            if event.button == 1 and self.shift_is_held:
                if event.xdata is not None and event.ydata is not None:
                    self.polygon[1].append(int(np.round(event.xdata)))
                    self.polygon[0].append(int(np.round(event.ydata)))
                    print(
                        f'y: {np.round(event.ydata):5.0f}, x: {np.round(event.xdata):5.0f}')
            elif event.button == 3 and self.shift_is_held:
                print('Deleted the last point...')
                del self.polygon[1][-1]
                del self.polygon[0][-1]

            line.set_xdata(self.polygon[1])
            line.set_ydata(self.polygon[0])
            fig.canvas.draw()

        def handle_close(event):
            """On closing."""
            self.polygon = np.asarray(self.polygon).T
            for i, point in enumerate(self.polygon):
                print(f'{i+1}. point: x ={point[1]:5.0f}, y ={point[0]:5.0f}')

            # Add points to video object
            video.points = self.observed_pixels()
            video.polygon = self.polygon

        canvas = FigureCanvasTkAgg(fig, root) # Tkinter
        canvas.get_tk_widget().pack(side='top', fill='both', expand=1) # Tkinter
        NavigationToolbar2Tk(canvas, root) # Tkinter

        # Connecting functions to event manager
        fig.canvas.mpl_connect('key_press_event', on_key_press)
        fig.canvas.mpl_connect('key_release_event', on_key_release)
        fig.canvas.mpl_connect('button_press_event', onclick)
        fig.canvas.mpl_connect('close_event', handle_close)  # on closing the figure
        
        root.mainloop()

    def observed_pixels(self):
        x = self.polygon[:, 1]
        y = self.polygon[:, 0]

        _polygon = np.asarray([x, y]).T

        x_low = min(x)
        x_high = max(x)
        y_low = min(y)
        y_high = max(y)

        # Get only the points in selected polygon
        inside = []
        for x_ in range(x_low, x_high):
            for y_ in range(y_low, y_high):
                if self.inside_polygon(x_, y_, _polygon) is True:
                    inside.append([y_, x_])  # Change indices (height, width)
        inside = np.asarray(inside)  # Indices of points in the polygon

        # Points outside the polygon have gradient of value 0
        g0 = np.zeros_like(self.gradient_0)
        g1 = np.zeros_like(self.gradient_1)
        g0[inside[:, 0], inside[:, 1]] = self.gradient_0[inside[:, 0], inside[:, 1]]
        g1[inside[:, 0], inside[:, 1]] = self.gradient_1[inside[:, 0], inside[:, 1]]

        if self.axis == 0:
            g = g0
        elif self.axis == 1:
            g = g1
        elif self.axis is None:
            g = g0**2 + g1**2
        else:
            raise Exception(f'axis value {self.axis} is not valid. Please pick 0, 1 or None')
        
        indices = []
        for i in range(y_low, y_high, self.subset[0]):
            for j in range(x_low, x_high, self.subset[1]):
                _g = g[i:i+self.subset[0], j:j+self.subset[1]]
                _ = np.argmax(np.abs(_g))
                ind = np.unravel_index(_, _g.shape)
                indices.append([i+ind[0], j+ind[1]])

        return np.asarray(indices)

    def inside_polygon(self, x, y, points):
        """Return True if a coordinate (x, y) is inside a polygon defined by
        a list of verticies [(x1, y1), (x2, x2), ... , (xN, yN)].

        Reference: http://www.ariel.com.au/a/python-point-int-poly.html
        """
        n = len(points)
        inside = False
        p1x, p1y = points[0]
        for i in range(1, n + 1):
            p2x, p2y = points[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / \
                                (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside
